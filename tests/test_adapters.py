from datetime import datetime
import json
import logging
import logging.handlers

from kombu import Exchange, Queue
from mock import Mock
from nameko.containers import WorkerContext
from nameko.contextdata import (
    LANGUAGE_CONTEXT_KEY,
    USER_AGENT_CONTEXT_KEY,
    USER_ID_CONTEXT_KEY,
)
from nameko.events import EventHandler, event_handler
from nameko.messaging import Consumer, consume
from nameko.rpc import rpc, Rpc
from nameko.web.handlers import http, HttpRequestHandler
from nameko.testing.utils import get_extension
import pytest
from werkzeug.test import create_environ
from werkzeug.wrappers import Request, Response

from nameko_entrypoint_logger import adapters, constants


@pytest.fixture
def tracker():

    class Tracker(logging.Handler):

        def __init__(self, *args, **kwargs):
            self.log_records = []
            super(Tracker, self).__init__(*args, **kwargs)

        def emit(self, log_record):
            self.log_records.append(log_record)

    return Tracker()


@pytest.fixture
def logger(tracker):

    logger = logging.getLogger('entrypoint_logger')
    logger.setLevel(logging.INFO)
    logger.addHandler(tracker)

    return logger


class TestEntrypointAdapter:

    @pytest.fixture
    def container(self, container_factory, rabbit_config, service_class):
        return container_factory(service_class, rabbit_config)

    @pytest.fixture
    def service_class(self):

        class Service(object):

            name = "some-service"

            @rpc
            def some_method(self, spam):
                pass

        return Service

    @pytest.fixture
    def worker_ctx(self, container, service_class):
        entrypoint = get_extension(
            container, Rpc, method_name='some_method')
        return WorkerContext(
            container, service_class, entrypoint, args=('some-arg',))

    @pytest.fixture
    def adapter(self, logger):
        adapter = adapters.EntrypointAdapter(logger, extra={})
        return adapter

    @pytest.mark.parametrize(
        'lifecycle_stage',
        (constants.Stage.request, constants.Stage.response),
    )
    def test_common_worker_data(
        self, adapter, tracker, worker_ctx, lifecycle_stage
    ):

        extra = {
            'lifecycle_stage': lifecycle_stage,
            'worker_ctx': worker_ctx,
            'result': None,
            'exc_info_': None,
            'timestamp': datetime(2017, 7, 7, 12, 0, 0),
            'response_time': 60.0,
        }

        adapter.info('spam', extra=extra)

        log_record = tracker.log_records[-1]

        data = getattr(log_record, constants.RECORD_ATTR)

        assert data['service'] == 'some-service'
        assert data['provider'] == 'Rpc'
        assert data['provider_name'] == 'some_method'
        assert data['entrypoint'] == 'some-service.some_method'
        assert data['call_id'] == worker_ctx.call_id
        assert data['call_stack'] == worker_ctx.call_id_stack
        assert data['lifecycle_stage'] == lifecycle_stage.value

    @pytest.mark.parametrize(
        'lifecycle_stage',
        (constants.Stage.request, constants.Stage.response),
    )
    def test_worker_ctx_data(
        self, adapter, tracker, worker_ctx, lifecycle_stage
    ):

        worker_ctx.data = {
            LANGUAGE_CONTEXT_KEY: 'en-gb',
            'some-other-key': 'should-be-ignored',
        }
        extra = {
            'lifecycle_stage': lifecycle_stage,
            'worker_ctx': worker_ctx,
            'result': None,
            'exc_info_': None,
            'timestamp': None,
            'response_time': None,
        }

        adapter.info('spam', extra=extra)

        log_record = tracker.log_records[-1]

        data = getattr(log_record, constants.RECORD_ATTR)

        assert data['context_data'] == {
            LANGUAGE_CONTEXT_KEY: 'en-gb',
            USER_ID_CONTEXT_KEY: None,
            USER_AGENT_CONTEXT_KEY: None,
        }

    @pytest.mark.parametrize(
        'lifecycle_stage',
        (constants.Stage.request, constants.Stage.response),
    )
    def test_call_args_data(
        self, adapter, tracker, worker_ctx, lifecycle_stage
    ):

        extra = {
            'lifecycle_stage': lifecycle_stage,
            'worker_ctx': worker_ctx,
            'result': None,
            'exc_info_': None,
            'timestamp': None,
            'response_time': None,
        }

        adapter.info('spam', extra=extra)

        log_record = tracker.log_records[-1]

        data = getattr(log_record, constants.RECORD_ATTR)

        assert data['call_args'] == {'spam': 'some-arg'}
        assert data['call_args_reducted'] == False

    @pytest.mark.parametrize(
        ('result_in', 'expected_result_out'),
        (
            (None, 'None'),
            ('spam', 'spam'),
            ({'spam': 'ham'}, {'spam': 'ham'}),
        ),
    )
    def test_result_data(
        self, adapter, tracker, worker_ctx, result_in, expected_result_out
    ):

        extra = {
            'lifecycle_stage': constants.Stage.response,
            'worker_ctx': worker_ctx,
            'result': result_in,
            'exc_info_': None,
            'timestamp': None,
            'response_time': None,
        }

        adapter.info('spam', extra=extra)

        log_record = tracker.log_records[-1]

        data = getattr(log_record, constants.RECORD_ATTR)

        assert data['return_args'] == expected_result_out
        assert data['status'] == constants.Status.success.value

    def test_error_data(self, adapter, tracker, worker_ctx):

        exception = ValueError("Invalid value")
        mock_exception = Mock()
        exc_info = (Exception, mock_exception, exception.__traceback__)

        extra = {
            'lifecycle_stage': constants.Stage.response,
            'worker_ctx': worker_ctx,
            'result': None,
            'exc_info_': exc_info,
            'timestamp': None,
            'response_time': None,
        }

        adapter.info('spam', extra=extra)

        log_record = tracker.log_records[-1]

        data = getattr(log_record, constants.RECORD_ATTR)

        # TODO ...

        assert data['status'] == constants.Status.error.value


    @pytest.fixture(params=[Rpc, EventHandler, Consumer])
    def entrypoint(self, request, container_factory, rabbit_config):

        EXCHANGE_NAME = "some-exchange"
        ROUTING_KEY = "some.routing.key"

        class Service(object):

            name = "some-service"
            exchange = Exchange(EXCHANGE_NAME)

            @rpc
            def rpc(self, payload):
                pass

            @event_handler("publisher", "property_updated")
            def event_handler(self, payload):
                pass

            @consume(queue=Queue(
                'service', exchange=exchange, routing_key=ROUTING_KEY))
            def consume(self, payload):
                pass

        container = container_factory(Service, rabbit_config)

        extension_class = request.param

        methods = {
            Rpc: 'rpc', EventHandler: 'event_handler', Consumer: 'consume'}

        entrypoint = get_extension(
            container, extension_class, method_name=methods[extension_class])
        worker_context = WorkerContext(
            container, Service, entrypoint, args=('spam',))

        return entrypoint, worker_context

    def test_various_entrypoints(self, adapter, entrypoint, tracker):

        entrypoint, worker_ctx = entrypoint

        extra = {
            'lifecycle_stage': constants.Stage.response,
            'worker_ctx': worker_ctx,
            'result': {'some': 'data'},
            'exc_info_': None,
            'timestamp': None,
            'response_time': None,
        }

        adapter.info('spam', extra=extra)

        log_record = tracker.log_records[-1]

        data = getattr(log_record, constants.RECORD_ATTR)

        assert data['return_args'] == {'some': 'data'}
        assert data['status'] == constants.Status.success.value
        assert data['provider'] == entrypoint.__class__.__name__
        assert data['provider_name'] == entrypoint.method_name


class TestHttpRequestHandlerAdapter:

    @pytest.fixture
    def container(self, container_factory, rabbit_config, service_class):
        return container_factory(service_class, rabbit_config)

    @pytest.fixture
    def service_class(self):

        class Service(object):

            name = "some-service"

            @http('GET', '/spam/<int:value>')
            def some_method(self, request, value):
                payload = {'value': value}
                return json.dumps(payload)

        return Service

    @pytest.fixture
    def worker_ctx(self, container, service_class):

        environ = create_environ(
            '/spam/1?test=123',
            'http://localhost:8080/',
            data=json.dumps({'foo': 'bar'}),
            content_type='application/json'
        )
        request = Request(environ)

        entrypoint = get_extension(
            container, HttpRequestHandler, method_name='some_method')
        return WorkerContext(
            container, service_class, entrypoint, args=(request, 1))

    @pytest.fixture
    def adapter(self, logger):
        adapter = adapters.HttpRequestHandlerAdapter(logger, extra={})
        return adapter

    @pytest.mark.parametrize(
        'lifecycle_stage',
        (constants.Stage.request, constants.Stage.response),
    )
    def test_call_args_data(
        self, adapter, tracker, worker_ctx, lifecycle_stage
    ):

        extra = {
            'lifecycle_stage': lifecycle_stage,
            'worker_ctx': worker_ctx,
            'result': Response(
                json.dumps({"value": 1}), mimetype='application/json'),
            'exc_info_': None,
            'timestamp': None,
            'response_time': None,
        }

        adapter.info('spam', extra=extra)

        log_record = tracker.log_records[-1]

        data = getattr(log_record, constants.RECORD_ATTR)

        call_args = data['call_args']

        assert call_args['value'] == 1

        request = call_args['request']

        assert request['method'] == 'GET'
        assert request['url'] == 'http://localhost:8080/spam/1?test=123'
        assert request['env']['server_port'] == '8080'
        assert request['env']['server_name'] == 'localhost'
        assert request['headers']['host'] == 'localhost:8080'
        assert request['headers']['content_type'] == 'application/json'
        assert request['headers']['content_length'] == '14'
        assert request['data'] == '{"foo": "bar"}'

    @pytest.mark.parametrize(
        ('data_in', 'content_type', 'expected_data_out'),
        (
            (
                json.dumps({'foo': 'bar'}),
                'application/json',
                '{"foo": "bar"}',
            ),
            (
                'foo=bar',
                'application/x-www-form-urlencoded',
                '{"foo": "bar"}',
            ),
            (
                'foo=bar',
                'text/plain',
                'foo=bar',
            ),
        )
    )
    def test_can_get_request_data(
        self, adapter, container, service_class, data_in, content_type,
        expected_data_out
    ):

        environ = create_environ(
            '/get/1?test=123',
            'http://localhost:8080/',
            data=data_in,
            content_type=content_type
        )
        request = Request(environ)

        entrypoint = get_extension(
            container, HttpRequestHandler, method_name='some_method')
        worker_ctx = WorkerContext(
            container, service_class, entrypoint, args=(request, 1))

        call_args, redacted = adapter.get_call_args(worker_ctx)

        assert redacted == False

        assert call_args['request']['data'] == expected_data_out
        assert call_args['request']['headers']['content_type'] == content_type

    @pytest.mark.parametrize(
        ('data', 'status_code', 'content_type'),
        (
            (
                '{"value": 1}',
                200,
                'application/json',
            ),
            (
                'foo',
                202,
                'text/plain',
            ),
            (
                'some error',
                400,
                'text/plain',
            ),
        )
    )
    def test_result_data(
        self, adapter, data, status_code, content_type
    ):

        response = Response(
            data, status=status_code, mimetype=content_type)

        result = adapter.get_result(response)

        assert result['result'] == data.encode('utf-8')
        assert result['status_code'] == status_code
        assert result['content_type'].startswith(content_type)
