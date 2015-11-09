import inspect
import json
import logging
import socket
from datetime import datetime
from traceback import format_tb
from weakref import WeakKeyDictionary

from kombu import Connection
from kombu.pools import connections, producers
from nameko.constants import (
    DEFAULT_RETRY_POLICY, DEFAULT_SERIALIZER, SERIALIZER_CONFIG_KEY)
from nameko.events import EventHandler
from nameko.extensions import DependencyProvider
from nameko.exceptions import safe_for_serialization, serialize
from nameko.messaging import AMQP_URI_CONFIG_KEY
from nameko.rpc import Rpc
from nameko.standalone.events import get_event_exchange
from nameko.utils import get_redacted_args
from nameko.web.handlers import HttpRequestHandler


class EntrypointLogger(DependencyProvider):
    """ Log arguments, results and debugging information
    of service entrypoints to RabbitMQ. Supported entrypoints: Rpc,
    EventHandler and HttpRequestHandler.
    """

    def __init__(self, exchange_name, routing_key, propagate=False):
        """
        :param exchange_name: exchange where events should be published to
        :param routing_key: event routing key
        :param propagate: propagate logs to the handlers of higher level
        """
        self.exchange_name = exchange_name
        self.routing_key = routing_key
        self.propagate = propagate
        self.logger = None
        self.worker_timestamps = WeakKeyDictionary()

    entrypoint_types = (Rpc, EventHandler, HttpRequestHandler)

    def setup(self):

        logger = logging.getLogger('entrypoint_logger')
        logger.setLevel(logging.INFO)
        logger.propagate = self.propagate

        dispatcher = event_dispatcher(
            self.container.config,
            self.exchange_name,
            self.routing_key
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

            result_json = None
            result_bytes = None

            if result:
                try:
                    result_bytes = len(result)
                    result_json = json.loads(result)
                except Exception:
                    result_json = safe_for_serialization(result)

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

            try:
                exc_repr = serialize(exc)
            except Exception:
                exc_repr = "[exc serialization failed]"

            data.update({
                'status': 'error',
                'exc_type': exc_info[0].__name__,
                'exc': exc_repr,
                'traceback': ''.join(format_tb(exc_info[2])),
                'expected_error': is_expected,
            })
        self.logger.info(dumps(data))


class EntrypointLoggingHandler(logging.Handler):

    def __init__(
        self,
        dispatcher
    ):

        self.dispatcher = dispatcher
        logging.Handler.__init__(self)

    def emit(self, message):
        self.dispatcher(message.getMessage())


def default(obj):
    """Default JSON serializer.
    :param obj: datetime
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise ValueError


def dumps(obj):
    return json.dumps(obj, default=default)


def event_dispatcher(nameko_config, exchange_name, routing_key):
    """ Return a function that dispatches nameko events.
    :param nameko_config: nameko configuration
    :param exchange_name: exchange where events should be published to
    :param routing_key: event routing key
    """

    def dispatch(event_data):
        """ Dispatch an event
        :param event_data: event payload
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
                    retry=True,
                    retry_policy=DEFAULT_RETRY_POLICY
                )

    return dispatch


def get_worker_data(worker_ctx):
    try:
        provider = worker_ctx.entrypoint
        service_name = worker_ctx.service_name
        provider_name = provider.method_name
        entrypoint = "{}.{}".format(service_name, provider_name)

        if hasattr(provider, 'sensitive_variables'):
            redacted_callargs = get_redacted_args(
                provider, *worker_ctx.args, **worker_ctx.kwargs)
        else:
            method = getattr(provider.container.service_cls,
                             provider.method_name)
            callargs = inspect.getcallargs(method, None, *worker_ctx.args,
                                           **worker_ctx.kwargs)
            del callargs['self']
            if 'request' in callargs:
                callargs['request'] = parse_http_request(callargs['request'])
            redacted_callargs = callargs

        data = {
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
            'call_args': redacted_callargs
        }
    except Exception as exc:
        data = {
            'error': "Error when gathering worker data: {}".format(str(exc))
        }
    return data


def parse_http_request(request):
    request_data = {
        'content_type': request.content_type,
        'url': request.url,
        'cookies': request.cookies,
        'method': request.method
    }

    post_data = request.get_data(as_text=True)

    if post_data:
        try:
            request_data['post_data'] = json.loads(post_data)
        except ValueError:
            request_data['post_data'] = post_data

    return request_data
