import json
import logging
from datetime import datetime

import pytest
from mock import MagicMock, Mock, patch
from nameko.containers import WorkerContext
from nameko.events import EventHandler, event_handler
from nameko.rpc import Rpc, rpc
from nameko.testing.utils import DummyProvider, get_extension
from nameko.web.handlers import HttpRequestHandler, http
from werkzeug.test import create_environ
from werkzeug.wrappers import Request

from nameko_entrypoint_logger import (
    BroadcastLogHandler, EntrypointLogger, event_dispatcher)

EXCHANGE_NAME = "logging_exchange"
ROUTING_KEY = "monitoring_event"

dispatcher = MagicMock()


class Service(object):
    name = "service"

    dispatch = dispatcher

    @rpc(expected_exceptions=ValueError)
    def rpc_method(self, foo):
        pass

    @http('GET', '/get/<int:value>')
    def get_method(self, request, value):
        payload = {'value': value}
        return json.dumps(payload)

    @event_handler("publisher", "routing_key")
    def handle_event(self, payload):
        self.dispatch({'success': True})


@pytest.fixture
def container(container_factory):
    return container_factory(Service, {})


@pytest.fixture
def entrypoint_logger(container):
    logger = EntrypointLogger(
        EXCHANGE_NAME, ROUTING_KEY
    ).bind(container, "service")

    logger.setup()

    return logger


@pytest.fixture
def rpc_worker_ctx(entrypoint_logger):
    entrypoint = get_extension(
        entrypoint_logger.container, Rpc, method_name="rpc_method"
    )

    return WorkerContext(
        entrypoint_logger.container, Service, entrypoint, args=("bar",)
    )


@pytest.fixture
def http_worker_ctx(entrypoint_logger):
    entrypoint = get_extension(
        entrypoint_logger.container,
        HttpRequestHandler,
        method_name="get_method"
    )

    environ = create_environ('/get/1', 'http://localhost:8080/')

    request = Request(environ)

    return WorkerContext(
        entrypoint_logger.container, Service, entrypoint, args=(request, 1)
    )


def test_setup(entrypoint_logger):
    assert BroadcastLogHandler in [
        type(handler) for handler in entrypoint_logger.logger.handlers
        if type(handler) == BroadcastLogHandler]

    assert entrypoint_logger.exchange_name == EXCHANGE_NAME
    assert entrypoint_logger.routing_key == ROUTING_KEY


def test_will_only_process_request_from_known_entrypoints(
    entrypoint_logger,
    mock_container
):
    mock_container.service_name = "service"
    worker_ctx = WorkerContext(mock_container, None, DummyProvider())

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_setup(worker_ctx)

    assert not logger.info.called


def test_will_only_process_results_from_known_entrypoints(
    entrypoint_logger,
    mock_container
):
    mock_container.service_name = "service"
    worker_ctx = WorkerContext(mock_container, None, DummyProvider())

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(worker_ctx)

    assert not logger.info.called


def test_rpc_request_is_logged(entrypoint_logger, rpc_worker_ctx):
    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_setup(rpc_worker_ctx)

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['call_args'] == {"foo": "bar"}


def test_rpc_response_is_logged(entrypoint_logger, rpc_worker_ctx):
    entrypoint_logger.worker_timestamps[rpc_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(rpc_worker_ctx, result={'bar': 'foo'})

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['call_args'] == {"foo": "bar"}
    assert worker_data['result'] == '{"bar": "foo"}'


def test_rpc_unexpected_exception_is_logged(entrypoint_logger, rpc_worker_ctx):
    exception = Exception("Something went wrong")
    exc_info = (Exception, exception, exception.__traceback__)

    entrypoint_logger.worker_timestamps[rpc_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(
            rpc_worker_ctx, result={'bar': 'foo'}, exc_info=exc_info
        )

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['expected_error'] == False
    assert worker_data['status'] == 'error'
    assert "Something went wrong" in str(worker_data['exc'])


def test_rpc_expected_exception_is_logged(entrypoint_logger, rpc_worker_ctx):
    exception = ValueError("Invalid value")
    exc_info = (Exception, exception, exception.__traceback__)

    entrypoint_logger.worker_timestamps[rpc_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(
            rpc_worker_ctx, result={'bar': 'foo'}, exc_info=exc_info
        )

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['expected_error'] == True
    assert worker_data['status'] == 'error'
    assert "Invalid value" in str(worker_data['exc'])


def test_can_fail_exception_repr(entrypoint_logger, rpc_worker_ctx):
    exception = ValueError("Invalid value")
    mock_exception = Mock()
    mock_exception.__repr__ = lambda s: (_ for _ in ()).throw(Exception())
    exc_info = (Exception, mock_exception, exception.__traceback__)

    entrypoint_logger.worker_timestamps[rpc_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(
            rpc_worker_ctx, result={'bar': 'foo'}, exc_info=exc_info
        )

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['exc'] == '[exc __repr__ failed]'


def test_http_request_is_logged(entrypoint_logger, http_worker_ctx):
    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_setup(http_worker_ctx)

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "HttpRequestHandler"
    assert worker_data['entrypoint'] == 'service.get_method'
    assert worker_data['call_args'] == {
        'request':
            {
                'method': 'GET',
                'content_type': '',
                'cookies': {},
                'url': 'http://localhost:8080/get/1'
            },
        'value': 1
    }


def test_http_response_is_logged(entrypoint_logger, http_worker_ctx):
    entrypoint_logger.worker_timestamps[http_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(http_worker_ctx, result={'value': 1})

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "HttpRequestHandler"
    assert json.loads(worker_data['result']) == {'value': 1}


def test_can_handle_non_json_results(entrypoint_logger, http_worker_ctx):
    entrypoint_logger.worker_timestamps[http_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(http_worker_ctx, result={None})

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['result'] == "[json dump failed]"


def test_event_handler_request_response_is_logged():
    pass


def test_event_handler_exception_is_logged():
    pass


def test_can_log_broadcast_events():
    logger = logging.getLogger('test')
    handler = BroadcastLogHandler(dispatcher)
    logger.addHandler(handler)
    message = {'foo': 'bar'}
    logger.info(json.dumps(message))

    (call_args,), _ = dispatcher.call_args

    assert dispatcher.called
    assert json.loads(call_args) == message


def test_will_dispatch_events():
    from nameko.constants import (
        AMQP_URI_CONFIG_KEY, SERIALIZER_CONFIG_KEY, DEFAULT_SERIALIZER)

    config = {
        SERIALIZER_CONFIG_KEY: DEFAULT_SERIALIZER,
        AMQP_URI_CONFIG_KEY: 'memory://'
    }

    dispatcher = event_dispatcher(config, EXCHANGE_NAME, ROUTING_KEY)

    from mock import ANY

    message = {'foo': 'bar'}

    with patch('nameko_entrypoint_logger.producers') as mock_producers:
        with mock_producers[ANY].acquire(block=True) as mock_producer:
            dispatcher(json.dumps(message))

    (msg,), config = mock_producer.publish.call_args

    assert json.loads(msg) == message
    assert config['routing_key'] == ROUTING_KEY


def test_end_to_end():
    # Esure worker_setup and worker_result are called
    pass
