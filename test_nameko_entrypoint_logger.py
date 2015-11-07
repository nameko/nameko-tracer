import logging
import json

from mock import Mock, patch, call
import pytest
from datetime import datetime
from nameko.containers import WorkerContext
from nameko.rpc import rpc, Rpc
from nameko.testing.services import dummy, entrypoint_hook, entrypoint_waiter
from nameko.testing.utils import get_extension
from nameko.events import EventHandler, event_handler

from nameko_entrypoint_logger import BroadcastLogHandler, EntrypointLogger

EXCHANGE_NAME = "logging_exchange"
ROUTING_KEY = "monitoring_event"

dispatcher = Mock()


class Service(object):
    name = "service"

    dispatch = dispatcher

    @rpc(expected_exceptions=ValueError)
    def rpc_method(self, foo):
        pass

    @event_handler("service_b", "performance_test_request")
    def handle_event(self, payload):
        self.dispatch({'success': True})



@pytest.fixture
def container(container_factory):
    return container_factory(Service, {})


@pytest.fixture
def entrypoint_logger(container):
    return EntrypointLogger(
        EXCHANGE_NAME, ROUTING_KEY
    ).bind(container, "service")


def test_setup(entrypoint_logger):
    entrypoint_logger.setup()

    assert BroadcastLogHandler in [
        type(handler) for handler in entrypoint_logger.logger.handlers
        if type(handler) == BroadcastLogHandler]

    assert entrypoint_logger.exchange_name == EXCHANGE_NAME
    assert entrypoint_logger.routing_key == ROUTING_KEY


def test_rpc_request_is_logged(entrypoint_logger):

    entrypoint = get_extension(
        entrypoint_logger.container, Rpc, method_name="rpc_method"
    )

    args = ("bar",)

    worker_ctx = WorkerContext(
        entrypoint_logger.container, Service, entrypoint, args=args
    )

    entrypoint_logger.setup()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_setup(worker_ctx)

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['call_args'] == {"foo": "bar"}


def test_rpc_response_is_logged(entrypoint_logger):

    entrypoint = get_extension(
        entrypoint_logger.container, Rpc, method_name="rpc_method"
    )

    args = ("bar",)

    worker_ctx = WorkerContext(
        entrypoint_logger.container, Service, entrypoint, args=args
    )

    entrypoint_logger.setup()

    entrypoint_logger.worker_timestamps[worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(worker_ctx, result={'bar': 'foo'})

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['call_args'] == {"foo": "bar"}
    assert worker_data['result'] == '{"bar": "foo"}'


def test_rpc_unexpected_exception_is_logged(entrypoint_logger):
    entrypoint = get_extension(
        entrypoint_logger.container, Rpc, method_name="rpc_method"
    )

    args = ("bar",)
    exception = Exception("Something went wrong")
    exc_info = (Exception, exception, exception.__traceback__)

    worker_ctx = WorkerContext(
        entrypoint_logger.container, Service, entrypoint, args=args
    )

    entrypoint_logger.setup()

    entrypoint_logger.worker_timestamps[worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(
            worker_ctx, result={'bar': 'foo'}, exc_info=exc_info
        )

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['expected_error'] == False
    assert worker_data['status'] == 'error'
    assert "Something went wrong" in str(worker_data['exc'])


def test_rpc_expected_exception_is_logged(entrypoint_logger):
    entrypoint = get_extension(
        entrypoint_logger.container, Rpc, method_name="rpc_method"
    )

    args = ("bar",)
    exception = ValueError("Invalid value")
    exc_info = (Exception, exception, exception.__traceback__)

    worker_ctx = WorkerContext(
        entrypoint_logger.container, Service, entrypoint, args=args
    )

    entrypoint_logger.setup()

    entrypoint_logger.worker_timestamps[worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(
            worker_ctx, result={'bar': 'foo'}, exc_info=exc_info
        )

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['expected_error'] == True
    assert worker_data['status'] == 'error'
    assert "Invalid value" in str(worker_data['exc'])


def test_event_handler_request_response_is_logged():
    pass


def test_event_handler_exception_is_logged():
    pass


def test_http_request_response_is_logged():
    pass


def test_http_exception_is_logged():
    pass


def test_end_to_end():
    # Esure worker_setup and worker_result are called
    pass
