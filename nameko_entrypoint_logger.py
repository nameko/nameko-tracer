from datetime import datetime
import json
import logging
import socket
import inspect
from traceback import format_tb
from weakref import WeakKeyDictionary

from kombu import Connection
from kombu.pools import producers, connections

from nameko.constants import (
    DEFAULT_RETRY_POLICY, SERIALIZER_CONFIG_KEY,
    DEFAULT_SERIALIZER)

from nameko.messaging import AMQP_URI_CONFIG_KEY
from nameko.standalone.events import get_event_exchange
from nameko.events import EventHandler
from nameko.rpc import Rpc
from nameko.web.handlers import HttpRequestHandler
from nameko.extensions import DependencyProvider
from nameko.utils import get_redacted_args


def default(obj):
    """Default JSON serializer."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise ValueError


def dumps(obj):
    return json.dumps(obj, default=default)


def event_dispatcher(nameko_config, exchange_name, routing_key, **kwargs):
    """ Return a function that dispatches nameko events.
    """

    kwargs = kwargs.copy()
    retry = kwargs.pop('retry', True)
    retry_policy = kwargs.pop('retry_policy', DEFAULT_RETRY_POLICY)

    def dispatch(event_data):
        """ Dispatch an event claiming to originate from `service_name` with
        the given `event_type` and `event_data`.
        """
        conn = Connection(nameko_config[AMQP_URI_CONFIG_KEY])

        serializer = nameko_config.get(
            SERIALIZER_CONFIG_KEY, DEFAULT_SERIALIZER)

        exchange = get_event_exchange(exchange_name)

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
                    retry=retry,
                    retry_policy=retry_policy,
                    **kwargs)
    return dispatch


def parse_request(request):

    return {
        'content_type': request.content_type,
        'url': request.url,
        'cookies': request.cookies,
        'method': request.method
    }


def get_worker_data(worker_ctx):
    provider = worker_ctx.entrypoint
    service_name = worker_ctx.service_name
    provider_name = provider.method_name
    entrypoint = "{}.{}".format(service_name, provider_name)

    if hasattr(provider, 'sensitive_variables'):
        redacted_callargs = get_redacted_args(
            provider, *worker_ctx.args, **worker_ctx.kwargs)
    else:
        method = getattr(provider.container.service_cls, provider.method_name)
        callargs = inspect.getcallargs(method, None, *worker_ctx.args, **worker_ctx.kwargs)
        del callargs['self']
        if 'request' in callargs:
            callargs['request'] = parse_request(callargs['request'])
        redacted_callargs = callargs

    return {
        'timestamp': datetime.utcnow(),
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
        'call_args': redacted_callargs,
    }


class BroadcastLogHandler(logging.Handler):
    # Broadcast log messages to RabbitMQ queue
    # TODO: Pre-queue in memory with eventlet.queue
    def __init__(
        self,
        dispatcher,
        force_tls=False,
        verbose=True,
        format=None
    ):
        self.dispatcher = dispatcher
        logging.Handler.__init__(self)

    def emit(self, message):
        self.dispatcher(message.getMessage())

    def flush(self):
        pass


class EntrypointLogger(DependencyProvider):
    def __init__(self, exchange_name, routing_key):
        self.exchange_name = exchange_name
        self.routing_key = routing_key

    entrypoint_types = (Rpc, EventHandler, HttpRequestHandler)

    def setup(self):

        logger = logging.getLogger('entrypoint_logger')
        logger.setLevel(logging.INFO)
        # TODO: When in public lib someone would want change to propagate?
        logger.propagate = False

        dispatcher = event_dispatcher(
            self.container.config,
            self.exchange_name,
            self.routing_key
        )
        handler = BroadcastLogHandler(dispatcher)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        self.logger = logger
        self.worker_timestamps = WeakKeyDictionary()

    def worker_setup(self, worker_ctx):
        if not isinstance(worker_ctx.entrypoint, self.entrypoint_types):
            return

        data = get_worker_data(worker_ctx)
        data.update({
            'lifecycle_stage': 'request',
        })

        self.logger.info(dumps(data))

        self.worker_timestamps[worker_ctx] = data['timestamp']

    def worker_result(self, worker_ctx, result=None, exc_info=None):

        if not isinstance(worker_ctx.entrypoint, self.entrypoint_types):
            return

        data = get_worker_data(worker_ctx)
        now = data['timestamp']
        worker_setup_time = self.worker_timestamps[worker_ctx]
        response_time = (now - worker_setup_time).total_seconds()

        data.update({
            'lifecycle_stage': 'response',
            'response_time': response_time,
        })

        if exc_info is None:
            try:
                result_json = dumps(result)
                result_bytes = len(result_json)
            except Exception:
                result_json = '[json dump failed]'
                result_bytes = None

            data.update({
                'status': 'success',
                'result_bytes': result_bytes,
                'result': result_json,
            })
        else:

            expected_exceptions = getattr(
                worker_ctx.entrypoint, 'expected_exceptions', None
            ) or tuple()  # can have attr set to None
            exc = exc_info[1]
            is_expected = isinstance(exc, expected_exceptions)

            if is_expected:
                level = logging.WARNING
            else:
                level = logging.ERROR
            self.logger.log(level, 'Exception', exc_info=exc_info)

            try:
                exc_repr = repr(exc)
            except Exception:
                exc_repr = "[exc __repr__ failed]"

            data.update({
                'status': 'error',
                'exc_type': exc_info[0].__name__,
                'exc': exc_repr,
                'traceback': ''.join(format_tb(exc_info[2])),
                'expected_error': is_expected,
            })
        self.logger.info(dumps(data))
