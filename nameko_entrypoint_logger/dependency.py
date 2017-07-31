import inspect
import json
import logging
import re
import socket
from datetime import datetime
from traceback import format_exception
from weakref import WeakKeyDictionary

import six
from nameko.exceptions import (
    ConfigurationError, safe_for_serialization, serialize)
from nameko.extensions import DependencyProvider
from nameko.messaging import Consumer
from nameko.rpc import Rpc
from nameko.utils import get_redacted_args
from nameko.web.handlers import HttpRequestHandler
from werkzeug.wrappers import Response

from nameko_entrypoint_logger.filters import (
    TruncateRequestFilter,
    TruncateResponseFilter,
)
from nameko_entrypoint_logger.formatters import JSONFormatter
from nameko_entrypoint_logger.handlers import PublisherHandler, logging_publisher


log = logging.getLogger(__name__)


class EntrypointLogger(DependencyProvider):
    """ Log arguments, results and debugging information
    of service entrypoints to RabbitMQ. Supported entrypoints: Rpc,
    Consumer (and it's derived implementation EventHandler) and
    HttpRequestHandler
    """

    required_config_keys = (
        'AMQP_URI',
        'EXCHANGE_NAME',
        'ROUTING_KEY'
    )

    entrypoint_types = (Rpc, Consumer, HttpRequestHandler)

    def __init__(self, propagate=False):
        """Initialise EntrypointLogger.

        :Parameters:
            propagate: bool
                Enable logs propagation to the handlers of higher level.
        """
        self.propagate = propagate
        self.logger = None
        self.enabled = False
        self.worker_timestamps = WeakKeyDictionary()

    def setup(self):

        config = self.container.config.get('ENTRYPOINT_LOGGING')
        if config and config.get('ENABLED'):
            self.enabled = True
        else:
            log.warning('EntrypointLogger is disabled')
            return

        for key in self.required_config_keys:
            if key not in config:
                raise ConfigurationError(
                    "ENTRYPOINT_LOGGING config missing key `{}`".format(key)
                )

        logger = logging.getLogger('entrypoint_logger')
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
        if logger.propagate:
            logger.propagate = self.propagate
        if not logger.handlers:
            publisher = logging_publisher(
                self.container.config
            )
            handler = PublisherHandler(publisher)
            #formatter = logging.Formatter('%(message)s')
            formatter = JSONFormatter()
            request_filter = TruncateRequestFilter()
            response_filter = TruncateResponseFilter()
            handler.setFormatter(formatter)
            logger.addFilter(request_filter)
            logger.addFilter(response_filter)
            logger.addHandler(handler)

        self.logger = logger

    def _get_base_worker_data(self, worker_ctx):
        timestamp = datetime.utcnow()
        try:
            call_args = get_call_args(worker_ctx)

            provider = worker_ctx.entrypoint
            service_name = worker_ctx.service_name
            provider_name = provider.method_name
            entrypoint = "{}.{}".format(service_name, provider_name)

            return {
                'timestamp': timestamp,
                'provider': type(provider).__name__,
                'hostname': socket.gethostname(),
                'service': service_name,
                'provider_name': provider_name,
                'entrypoint': entrypoint,
                'call_id': worker_ctx.call_id,
                'call_stack': worker_ctx.call_id_stack,
                'context_data': {
                    'language': worker_ctx.data.get('language'),
                    'user_id': worker_ctx.data.get('user_id'),
                    'user_agent': worker_ctx.data.get('user_agent'),
                },
                'call_args': call_args,

            }
        except Exception as exc:
            return {
                'timestamp': timestamp,
                'error': "Error when gathering worker data: {}".format(exc)
            }

    def _get_request_worker_data(self, worker_ctx):
        data = self._get_base_worker_data(worker_ctx)
        data['lifecycle_stage'] = 'request'
        return data

    def _get_response_worker_data(self, worker_ctx, result, exc_info):
        data = self._get_base_worker_data(worker_ctx)
        data['lifecycle_stage'] = 'response'
        data['response_time'] = self.calculate_response_time(
            data, worker_ctx
        )

        if exc_info is None:
            data['status'] = 'success'

            return_args = get_return_args(result)
            if return_args:
                data['return_args'] = return_args

        else:
            data['status'] = 'error'
            data['exception'] = get_exception(worker_ctx, exc_info)
        return data

    def worker_setup(self, worker_ctx):
        try:
            if not self.should_log(worker_ctx.entrypoint):
                return

            data = self._get_request_worker_data(worker_ctx)
            self.logger.info('entrypoint request', extra={'data': data})

            self.worker_timestamps[worker_ctx] = data['timestamp']

        except Exception as exc:
            log.error(exc)

    def worker_result(self, worker_ctx, result=None, exc_info=None):
        try:
            if not self.should_log(worker_ctx.entrypoint):
                return

            data = self._get_response_worker_data(worker_ctx, result, exc_info)
            self.logger.info('entrypoint response', extra={'data': data})

        except Exception as exc:
            log.error(exc)

    def calculate_response_time(self, data, worker_ctx):
        now = data['timestamp']
        worker_setup_time = self.worker_timestamps[worker_ctx]
        return (now - worker_setup_time).total_seconds()

    def should_log(self, entrypoint):
        return self.enabled and isinstance(entrypoint, self.entrypoint_types)


def get_entrypoint_call_args(worker_ctx):
    provider = worker_ctx.entrypoint
    method = getattr(provider.container.service_cls, provider.method_name)

    call_args = inspect.getcallargs(
        method, None, *worker_ctx.args, **worker_ctx.kwargs
    )

    del call_args['self']

    return call_args


def get_call_args(worker_ctx):
    provider = worker_ctx.entrypoint
    call_args = {}
    if getattr(provider, 'sensitive_variables', None):
        redacted_callargs = get_redacted_args(
            provider, *worker_ctx.args, **worker_ctx.kwargs)

        return {'redacted_args': to_string(redacted_callargs)}

    # TODO: HttpRequestHandler should support sensitive_variables
    # Also get_redacted_args should be tolerant of
    # entrypoints that don't define them
    args = get_entrypoint_call_args(worker_ctx)
    request = args.pop('request', None)

    call_args = {'args': to_string(safe_for_serialization(args))}
    if request:
        call_args['request'] = get_http_request(request)
    return call_args


def get_return_args(result):
    if isinstance(result, Response):
        # spceific case for processing HTTP response
        return {
            'content_type': result.content_type,
            'result': to_string(result.get_data()),
            'status_code': result.status_code,
            'result_bytes': result.content_length,
        }
    # All other responses
    result_string = to_string(safe_for_serialization(result))
    return {
        'result_bytes': len(result_string),
        'result': result_string,
    }


def get_exception(worker_ctx, exc_info):
    expected_exceptions = getattr(
        worker_ctx.entrypoint, 'expected_exceptions', None
    ) or tuple()  # can have attr set to None
    exc = exc_info[1]
    is_expected = isinstance(exc, expected_exceptions)

    try:
        exc_repr = serialize(exc)
    except Exception:
        exc_repr = "[exc serialization failed]"

    try:
        exc_traceback = ''.join(format_exception(*exc_info))
    except Exception:
        exc_traceback = "[format_exception failed]"

    return {
        'exc_type': exc_info[0].__name__,
        'exc': to_string(exc_repr),
        'traceback': exc_traceback,
        'expected_error': is_expected,
    }


def get_http_request(request):
    data = request.data or request.form
    return {
        'url': request.url,
        'method': request.method,
        'data': to_string(data),
        'headers': dict(get_headers(request.environ)),
        'env': dict(get_environ(request.environ)),
    }


def get_headers(environ):
    """
    Returns only proper HTTP headers.
    """
    for key, value in six.iteritems(environ):
        key = str(key)
        if key.startswith('HTTP_') and key not in \
                ('HTTP_CONTENT_TYPE', 'HTTP_CONTENT_LENGTH'):
            yield key[5:].lower(), str(value)
        elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            yield key.lower(), str(value)


def get_environ(environ):
    """
    Returns our whitelisted environment variables.
    """
    for key in ('REMOTE_ADDR', 'SERVER_NAME', 'SERVER_PORT'):
        if key in environ:
            yield key.lower(), str(environ[key])


def to_string(value):
    if isinstance(value, six.string_types):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")
