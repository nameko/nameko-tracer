import json
import logging
from datetime import datetime

import pytest
from mock import MagicMock, Mock, patch
from nameko.constants import AMQP_URI_CONFIG_KEY
from nameko.containers import WorkerContext
from nameko.events import EventHandler, event_handler
from nameko.rpc import Rpc, rpc
from nameko.testing.services import entrypoint_hook, entrypoint_waiter
from nameko.testing.utils import DummyProvider, get_extension
from nameko.web.handlers import HttpRequestHandler, http
from werkzeug.test import create_environ
from werkzeug.wrappers import Request

from nameko_entrypoint_logger import (
    EntrypointLogger, EntrypointLoggingHandler,
    dumps, event_dispatcher, get_worker_data)

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
        pass


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
def http_entrypoint(entrypoint_logger):
    return get_extension(
        entrypoint_logger.container,
        HttpRequestHandler,
        method_name="get_method"
    )

@pytest.fixture
def http_worker_ctx(entrypoint_logger, http_entrypoint):
    environ = create_environ(
        '/get/1',
        'http://localhost:8080/',
        data=json.dumps({'foo': 'bar'})
    )

    request = Request(environ)

    return WorkerContext(
        entrypoint_logger.container, Service, http_entrypoint, args=(request, 1)
    )


@pytest.fixture
def event_worker_ctx(entrypoint_logger):
    entrypoint = get_extension(
        entrypoint_logger.container, EventHandler, method_name="handle_event"
    )

    return WorkerContext(
        entrypoint_logger.container, Service, entrypoint, args=("bar",)
    )


@pytest.fixture
def config():
    return {
        AMQP_URI_CONFIG_KEY: 'memory://'
    }


def test_setup(entrypoint_logger):
    assert EntrypointLoggingHandler in [
        type(handler) for handler in entrypoint_logger.logger.handlers
        if type(handler) == EntrypointLoggingHandler]

    assert entrypoint_logger.exchange_name == EXCHANGE_NAME
    assert entrypoint_logger.routing_key == ROUTING_KEY


def test_will_not_process_request_from_unknown_entrypoints(
    entrypoint_logger,
    mock_container
):
    mock_container.service_name = "service"
    worker_ctx = WorkerContext(mock_container, None, DummyProvider())

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_setup(worker_ctx)

    assert not logger.info.called


def test_will_not_process_results_from_unknown_entrypoints(
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
        entrypoint_logger.worker_result(rpc_worker_ctx, result='{"bar": "foo"}')

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['call_args'] == {"foo": "bar"}
    assert worker_data['result'] == {"bar": "foo"}


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
                'post_data': {'foo': 'bar'},
                'content_type': '',
                'cookies': {},
                'url': 'http://localhost:8080/get/1'
            },
        'value': 1
    }


def test_http_response_is_logged(entrypoint_logger, http_worker_ctx):
    entrypoint_logger.worker_timestamps[http_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(http_worker_ctx, result='{"value": 1}')

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "HttpRequestHandler"
    assert worker_data['result'] == {'value': 1}


def test_can_handle_none_json_request(entrypoint_logger, http_entrypoint):

    environ = create_environ(
        '/get/1',
        'http://localhost:8080/',
        data="foo"
    )

    request = Request(environ)

    http_worker_ctx = WorkerContext(
        entrypoint_logger.container, Service, http_entrypoint, args=(request, 1)
    )

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_setup(http_worker_ctx)

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['call_args']['request']['post_data'] == "foo"


def test_can_handle_none_json_results(entrypoint_logger, http_worker_ctx):
    entrypoint_logger.worker_timestamps[http_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(http_worker_ctx, result="abc")

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['result'] == "abc"


def test_event_handler_request_is_logged(
    entrypoint_logger, event_worker_ctx
):

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_setup(event_worker_ctx)

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "EventHandler"
    assert worker_data['call_args'] == {"payload": "bar"}


def test_event_handler_response_is_logged(
    entrypoint_logger, event_worker_ctx
):

    entrypoint_logger.worker_timestamps[event_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(
            event_worker_ctx, result=None)

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "EventHandler"
    assert worker_data['call_args'] == {"payload": "bar"}
    assert worker_data['result'] is None


def test_entrypoint_logging_handler_will_dispatch_log_message():
    logger = logging.getLogger('test')
    handler = EntrypointLoggingHandler(dispatcher)
    logger.addHandler(handler)
    message = {'foo': 'bar'}
    logger.info(json.dumps(message))

    (call_args,), _ = dispatcher.call_args

    assert dispatcher.called
    assert json.loads(call_args) == message


def test_event_dispatcher_will_dispatch_logs(config):

    dispatcher = event_dispatcher(config, EXCHANGE_NAME, ROUTING_KEY)

    from mock import ANY

    message = {'foo': 'bar'}

    with patch('nameko_entrypoint_logger.producers') as mock_producers:
        with mock_producers[ANY].acquire(block=True) as mock_producer:
            dispatcher(json.dumps(message))

    (msg,), config = mock_producer.publish.call_args

    assert json.loads(msg) == message
    assert config['routing_key'] == ROUTING_KEY


def test_unexpected_exception_is_logged(entrypoint_logger, rpc_worker_ctx):
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


def test_expected_exception_is_logged(entrypoint_logger, rpc_worker_ctx):
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


def test_can_handle_failed_exception_repr(entrypoint_logger, rpc_worker_ctx):
    exception = ValueError("Invalid value")
    mock_exception = Mock()
    exc_info = (Exception, mock_exception, exception.__traceback__)

    entrypoint_logger.worker_timestamps[rpc_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(
            rpc_worker_ctx, result={'bar': 'foo'}, exc_info=exc_info
        )

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['exc'] == '[exc serialization failed]'


def test_end_to_end(container_factory, config):

    class TestService(object):
        name = "service"

        entrypoint_logger = EntrypointLogger(EXCHANGE_NAME, ROUTING_KEY)

        @rpc
        def rpc_method(self):
            pass

    container = container_factory(TestService, config)
    container.start()

    logger = get_extension(container, EntrypointLogger)

    with patch.object(logger, 'logger') as logger:
        with entrypoint_hook(container, 'rpc_method') as rpc_method:
            with entrypoint_waiter(container, 'rpc_method'):
                rpc_method()

    assert logger.info.call_count == 2


def test_default_json_serializer_will_raise_value_error():
    with pytest.raises(ValueError):
        dumps({'weird_value': {None}})


def test_can_handle_exception_when_getting_worker_data():
    worker_ctx = Mock()
    error_message = "Something went wrong."
    with patch('nameko_entrypoint_logger.hasattr') as hasattr_mock:
        hasattr_mock.side_effect = Exception(error_message)
        data = get_worker_data(worker_ctx)

    assert error_message in data['error']
