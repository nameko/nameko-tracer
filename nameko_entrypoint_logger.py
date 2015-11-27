import inspect
import json
import logging
import socket
from datetime import datetime
from traceback import format_tb
from weakref import WeakKeyDictionary
import six
from kombu import Connection, Exchange
from kombu.pools import connections, producers
from nameko.constants import (
    DEFAULT_RETRY_POLICY, DEFAULT_SERIALIZER,
    SERIALIZER_CONFIG_KEY
)
from nameko.events import EventHandler
from nameko.exceptions import safe_for_serialization, serialize
from nameko.extensions import DependencyProvider
from nameko.messaging import AMQP_URI_CONFIG_KEY
from nameko.rpc import Rpc
from nameko.utils import get_redacted_args
from nameko.web.handlers import HttpRequestHandler
from werkzeug.wrappers import Response

log = logging.getLogger(__name__)


class EntrypointLogger(DependencyProvider):
    """ Log arguments, results and debugging information
    of service entrypoints to RabbitMQ. Supported entrypoints: Rpc,
    EventHandler and HttpRequestHandler.
    """

    entrypoint_types = (Rpc, EventHandler, HttpRequestHandler)

    def __init__(self, propagate=False):
        """Initialise EntrypointLogger.

        :Parameters:
            propagate: bool
                Enable logs propagation to the handlers of higher level.
        """
        self.propagate = propagate
        self.logger = None
        self.worker_timestamps = WeakKeyDictionary()

    def setup(self):

        entrypoint_config = self.container.config['ENTRYPOINT_LOGGING']

        exchange_name = entrypoint_config['EXCHANGE_NAME']
        routing_key = entrypoint_config['ROUTING_KEY']

        logger = logging.getLogger('entrypoint_logger')
        logger.setLevel(logging.INFO)
        logger.propagate = self.propagate

        dispatcher = logging_dispatcher(
            self.container.config,
            exchange_name,
            routing_key
        )
        handler = EntrypointLoggingHandler(dispatcher)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        self.logger = logger

    def worker_setup(self, worker_ctx):

        if not isinstance(worker_ctx.entrypoint, self.entrypoint_types):
            return

        data = get_worker_data(worker_ctx)

        data.update({
            'lifecycle_stage': 'request'
        })

        self.logger.info(dumps(data))

        self.worker_timestamps[worker_ctx] = data['timestamp']

    def worker_result(self, worker_ctx, result=None, exc_info=None):

        if not isinstance(worker_ctx.entrypoint, self.entrypoint_types):
            return

        data = get_worker_data(worker_ctx)

        response_time = self.calculate_response_time(data, worker_ctx)

        data.update({
            'lifecycle_stage': 'response',
            'response_time': response_time
        })

        if exc_info is None:

            data['status'] = 'success'

            data.update(
                process_response(result)
            )
        else:

            data['status'] = 'error'

            data.update(
                process_exception(worker_ctx, exc_info)
            )
        self.logger.info(dumps(data))

    def calculate_response_time(self, data, worker_ctx):
        now = data['timestamp']
        worker_setup_time = self.worker_timestamps[worker_ctx]
        return (now - worker_setup_time).total_seconds()


class EntrypointLoggingHandler(logging.Handler):
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        super(EntrypointLoggingHandler, self).__init__()

    def emit(self, message):
        self.dispatcher(message.getMessage())


def default(obj):
    """Default JSON serializer.

    :Parameters:
        obj: Might be a datetime
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise ValueError


def dumps(obj):
    return json.dumps(obj, default=default)


def logging_dispatcher(nameko_config, exchange_name, routing_key):
    """ Return a function that dispatches nameko events.

    :Parameters:
        nameko_config: dict
            Nameko configuration
        exchange_name: str
            Exchange where events should be published to
        routing_key: str
            Event routing key
    """

    def dispatch(event_data):
        """ Dispatch an event

        :Parameters:
            event_data: dict
                event payload
        """
        conn = Connection(nameko_config[AMQP_URI_CONFIG_KEY])

        serializer = nameko_config.get(
            SERIALIZER_CONFIG_KEY, DEFAULT_SERIALIZER)

        exchange = Exchange(exchange_name)

        try:

            with connections[conn].acquire(block=True) as connection:
                exchange.maybe_bind(connection)
                with producers[conn].acquire(block=True) as producer:
                    msg = event_data
                    producer.publish(
                        msg,
                        exchange=exchange,
                        declare=[exchange],
                        serializer=serializer,
                        routing_key=routing_key,
                        retry=True,
                        retry_policy=DEFAULT_RETRY_POLICY
                    )
        except Exception as exc:
            log.error(exc)

    return dispatch


def get_worker_data(worker_ctx):
    data = {
        'timestamp': datetime.utcnow()
    }

    try:
        provider = worker_ctx.entrypoint
        service_name = worker_ctx.service_name
        provider_name = provider.method_name
        entrypoint = "{}.{}".format(service_name, provider_name)

        if hasattr(provider, 'sensitive_variables'):
            redacted_callargs = get_redacted_args(
                provider, *worker_ctx.args, **worker_ctx.kwargs)

            call_args = {
                'redacted_args': to_string(redacted_callargs)
            }

        else:
            # TODO: HttpRequestHandler should support sensitive_variables
            # Also get_redacted_args should be tolerant of
            # entrypoints that don't define them
            args = get_entrypoint_call_args(worker_ctx)

            call_args = {}

            if 'request' in args:
                call_args['request'] = get_http_request(
                    args.pop('request')
                )

            call_args['args'] = to_string(safe_for_serialization(args))

        data.update({
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
            'call_args': call_args
        })
    except Exception as exc:
        data.update({
            'error': "Error when gathering worker data: {}".format(str(exc))
        })
    return data


def get_entrypoint_call_args(worker_ctx):
    """Get arguments passed to worker container method)"""

    provider = worker_ctx.entrypoint
    method = getattr(provider.container.service_cls, provider.method_name)

    call_args = inspect.getcallargs(
        method, None, *worker_ctx.args, **worker_ctx.kwargs
    )

    del call_args['self']

    return call_args


def process_response(result):
    data = {}

    if isinstance(result, Response):
        data['return_args'] = get_http_response(result)
    else:
        result_string = to_string(safe_for_serialization(result))
        result_bytes = len(result_string)
        data['return_args'] = {
            'result_bytes': result_bytes,
            'result': result_string,
        }
    return data


def process_exception(worker_ctx, exc_info):
    expected_exceptions = getattr(
        worker_ctx.entrypoint, 'expected_exceptions', None
    ) or tuple()  # can have attr set to None
    exc = exc_info[1]
    is_expected = isinstance(exc, expected_exceptions)

    try:
        exc_repr = serialize(exc)
    except Exception:
        exc_repr = "[exc serialization failed]"

    return {
        'exc_type': exc_info[0].__name__,
        'exc': exc_repr,
        'traceback': ''.join(format_tb(exc_info[2])),
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


def get_http_response(response):
    return {
        'content_type': response.content_type,
        'result': to_string(response.get_data()),
        'status_code': response.status_code,
        'result_bytes': response.content_length,
    }


def get_headers(environ):
    """
    Returns only proper HTTP headers.
    """
    for key, value in six.iteritems(environ):
        key = str(key)
        if key.startswith('HTTP_') and key not in \
            ('HTTP_CONTENT_TYPE', 'HTTP_CONTENT_LENGTH'):
            yield key[5:].lower(), value
        elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            yield key.lower(), value


def get_environ(environ):
    """
    Returns our whitelisted environment variables.
    """
    for key in ('REMOTE_ADDR', 'SERVER_NAME', 'SERVER_PORT'):
        if key in environ:
            yield key.lower(), environ[key]


def to_string(value):
    if isinstance(value, six.string_types):
        return value
    if isinstance(value, dict):
        return json.dumps(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")
