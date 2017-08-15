from datetime import datetime
import logging

from mock import call, patch, Mock
from nameko.containers import WorkerContext
from nameko.web.handlers import HttpRequestHandler
from nameko.testing.services import dummy, entrypoint_hook
from nameko.testing.utils import DummyProvider
import pytest

from nameko_tracer import adapters, constants, Tracer


@pytest.fixture
def tracker():

    class Tracker(logging.Handler):

        def __init__(self, *args, **kwargs):
            self.log_records = []
            super(Tracker, self).__init__(*args, **kwargs)

        def emit(self, log_record):
            self.log_records.append(log_record)

    tracker = Tracker()

    logger = logging.getLogger(constants.LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.addHandler(tracker)

    return tracker


@pytest.yield_fixture
def mocked_datetime():
    with patch('nameko_tracer.dependency.datetime') as dt:
        yield dt


def test_successful_result(container_factory, mocked_datetime, tracker):

    request_timestamp = datetime(2017, 7, 7, 12, 0, 0)
    response_timestamp = datetime(2017, 7, 7, 12, 1, 0)
    mocked_datetime.utcnow.side_effect = [
        request_timestamp, response_timestamp]

    class Service(object):

        name = "some-service"

        tracer = Tracer()

        @dummy
        def some_method(self, spam):
            pass

    container = container_factory(Service, {})
    container.start()

    with entrypoint_hook(container, 'some_method') as some_method:
        some_method('ham')

    assert len(tracker.log_records) == 2

    setup_record, result_record = tracker.log_records

    assert setup_record.msg == 'entrypoint call trace'
    assert setup_record.levelno == logging.INFO
    assert result_record.msg == 'entrypoint result trace'
    assert result_record.levelno == logging.INFO

    setup_details = getattr(setup_record, constants.TRACE_KEY)

    assert setup_details[constants.TIMESTAMP_KEY] == request_timestamp
    assert (
        setup_details[constants.STAGE_KEY] ==
        constants.Stage.request.value)

    result_details = getattr(result_record, constants.TRACE_KEY)

    assert result_details[constants.TIMESTAMP_KEY] == response_timestamp
    assert result_details[constants.RESPONSE_TIME_KEY] == 60.0
    assert (
        result_details[constants.STAGE_KEY] ==
        constants.Stage.response.value)
    assert (
        result_details[constants.RESPONSE_STATUS_KEY] ==
        constants.Status.success.value)


def test_failing_result(container_factory, mocked_datetime, tracker):

    request_timestamp = datetime(2017, 7, 7, 12, 0, 0)
    response_timestamp = datetime(2017, 7, 7, 12, 1, 0)
    mocked_datetime.utcnow.side_effect = [
        request_timestamp, response_timestamp]

    class SomeError(Exception):
        pass

    class Service(object):

        name = "some-service"

        tracer = Tracer()

        @dummy
        def some_method(self, spam):
            raise SomeError('Yo!')

    container = container_factory(Service, {})
    container.start()

    with pytest.raises(SomeError):
        with entrypoint_hook(container, 'some_method') as some_method:
            some_method('ham')

    assert len(tracker.log_records) == 2

    setup_record, result_record = tracker.log_records

    assert setup_record.msg == 'entrypoint call trace'
    assert setup_record.levelno == logging.INFO
    assert result_record.msg == 'entrypoint result trace'
    assert result_record.levelno == logging.WARNING

    setup_details = getattr(setup_record, constants.TRACE_KEY)

    assert setup_details[constants.TIMESTAMP_KEY] == request_timestamp
    assert (
        setup_details[constants.STAGE_KEY] ==
        constants.Stage.request.value)

    result_details = getattr(result_record, constants.TRACE_KEY)

    assert result_details[constants.TIMESTAMP_KEY] == response_timestamp
    assert result_details[constants.RESPONSE_TIME_KEY] == 60.0
    assert (
        result_details[constants.STAGE_KEY] ==
        constants.Stage.response.value)
    assert (
        result_details[constants.RESPONSE_STATUS_KEY] ==
        constants.Status.error.value)


@patch('nameko_tracer.adapters.DefaultAdapter.info')
@patch('nameko_tracer.dependency.logger')
def test_erroring_setup_adapter(logger, info, container_factory, tracker):

    class SomeError(Exception):
        pass

    class Service(object):

        name = "some-service"

        tracer = Tracer()

        @dummy
        def some_method(self, spam):
            pass

    container = container_factory(Service, {})
    container.start()

    info.side_effect = [
        SomeError('Yo!'),
        None
    ]
    with entrypoint_hook(container, 'some_method') as some_method:
        some_method('ham')

    # nothing logged by entrypoint logger
    assert len(tracker.log_records) == 0

    # warning logged by module logger
    assert logger.warning.call_args == call(
        'Failed to log entrypoint trace', exc_info=True)


@patch('nameko_tracer.adapters.DefaultAdapter.info')
@patch('nameko_tracer.dependency.logger')
def test_erroring_result_adapter(logger, info, container_factory, tracker):

    class SomeError(Exception):
        pass

    class Service(object):

        name = "some-service"

        tracer = Tracer()

        @dummy
        def some_method(self, spam):
            pass

    container = container_factory(Service, {})
    container.start()

    info.side_effect = [
        Mock(return_value=(Mock(), Mock())),
        SomeError('Yo!')
    ]
    with entrypoint_hook(container, 'some_method') as some_method:
        some_method('ham')

    # nothing logged by entrypoint logger
    assert len(tracker.log_records) == 0

    # warning logged by module logger
    assert logger.warning.call_args == call(
        'Failed to log entrypoint trace', exc_info=True)


@patch('nameko_tracer.adapters.HttpRequestHandlerAdapter.info')
@patch('nameko_tracer.adapters.DefaultAdapter.info')
def test_default_adapters(default_info, http_info, mock_container):

    mock_container.service_name = 'dummy'
    mock_container.config = {}
    tracer = Tracer().bind(mock_container, 'logger')
    tracer.setup()

    default_worker_ctx = WorkerContext(mock_container, None, DummyProvider())
    http_worker_ctx = WorkerContext(
        mock_container, None, HttpRequestHandler('GET', 'http://yo'))

    calls = [
        tracer.worker_setup,
        tracer.worker_result,
        tracer.worker_setup,
        tracer.worker_result
    ]

    for call_ in calls:
        call_(default_worker_ctx)
        call_(http_worker_ctx)

    assert default_info.call_count == 4
    assert http_info.call_count == 4


class CustomAdapter(adapters.DefaultAdapter):
    pass


@patch('nameko_tracer.adapters.DefaultAdapter.info')
@patch.object(CustomAdapter, 'info')
def test_config_adapters(default_info, custom_info, mock_container):

    mock_container.service_name = 'dummy'
    mock_container.config = {
        constants.CONFIG_KEY: {
            constants.ADAPTERS_CONFIG_KEY: {
                'nameko.web.handlers.HttpRequestHandler':
                    'test_dependency.CustomAdapter',
            }
        }
    }
    tracer = Tracer().bind(mock_container, 'logger')
    tracer.setup()

    default_worker_ctx = WorkerContext(mock_container, None, DummyProvider())
    http_worker_ctx = WorkerContext(
        mock_container, None, HttpRequestHandler('GET', 'http://yo'))

    calls = [
        tracer.worker_setup,
        tracer.worker_result,
        tracer.worker_setup,
        tracer.worker_result
    ]

    for call_ in calls:
        call_(default_worker_ctx)
        call_(http_worker_ctx)

    assert default_info.call_count == 4
    assert custom_info.call_count == 4
