import json
import logging
import re
import socket
from datetime import datetime

import pytest
from kombu import Exchange, Queue
from mock import ANY, call, MagicMock, Mock, patch
from nameko.constants import AMQP_URI_CONFIG_KEY
from nameko.containers import WorkerContext
from nameko.events import EventHandler, event_handler
from nameko.exceptions import ConfigurationError
from nameko.messaging import Consumer, consume
from nameko.rpc import Rpc, rpc
from nameko.testing.services import entrypoint_hook, entrypoint_waiter
from nameko.testing.utils import DummyProvider, get_extension
from nameko.web.handlers import HttpRequestHandler, http
from nameko_entrypoint_logger import (
    EntrypointLogger, EntrypointLoggingHandler, dumps, get_http_request,
    get_worker_data, logging_publisher, process_response, should_truncate)
from werkzeug.test import create_environ
from werkzeug.wrappers import Request, Response

EXCHANGE_NAME = "logging_exchange"
ROUTING_KEY = "monitoring_log"

publisher = MagicMock()


class CustomException(Exception):
    pass


class Service(object):
    name = "service"

    entrypoint_logger = EntrypointLogger()
    exchange = Exchange(EXCHANGE_NAME)

    @rpc(expected_exceptions=CustomException)
    def rpc_method(self, foo):
        pass

    @http('GET', '/get/<int:value>')
    def get_method(self, request, value):
        payload = {'value': value}
        return json.dumps(payload)

    @event_handler("publisher", "property_updated")
    def handle_event(self, payload):
        pass

    @consume(
        queue=Queue(
            'service', exchange=exchange, routing_key=ROUTING_KEY
        ))
    def custom_handler(self, payload):
        pass


@pytest.fixture
def config():
    return {
        AMQP_URI_CONFIG_KEY: 'memory://dev',
        'ENTRYPOINT_LOGGING': {
            'ENABLED': True,
            'AMQP_URI': 'memory://dev',
            'EXCHANGE_NAME': EXCHANGE_NAME,
            'ROUTING_KEY': ROUTING_KEY,
            'SERIALIZER': 'json',
            'CONTENT_TYPE': 'application/json'
        }
    }


@pytest.fixture
def container(container_factory, config):
    return container_factory(Service, config)


@pytest.fixture
def entrypoint_logger(container):
    logger = get_extension(container, EntrypointLogger)

    logger.setup()

    return logger


@pytest.fixture
def rpc_worker_ctx(container):
    entrypoint = get_extension(
        container, Rpc, method_name="rpc_method"
    )

    return WorkerContext(
        container, Service, entrypoint, args=("bar",)
    )


@pytest.fixture
def http_entrypoint(container):
    return get_extension(
        container, HttpRequestHandler, method_name="get_method"
    )


@pytest.fixture
def http_worker_ctx(container, http_entrypoint):
    environ = create_environ(
        '/get/1?test=123',
        'http://localhost:8080/',
        data=json.dumps({'foo': 'bar'}),
        content_type='application/json'
    )

    request = Request(environ)

    return WorkerContext(
        container, Service, http_entrypoint, args=(request, 1)
    )


@pytest.fixture
def event_worker_ctx(container):
    entrypoint = get_extension(
        container, EventHandler, method_name="handle_event"
    )

    return WorkerContext(
        container, Service, entrypoint, args=("bar",)
    )


@pytest.fixture
def consumer_worker_ctx(container):
    entrypoint = get_extension(
        container, Consumer, method_name="custom_handler"
    )

    return WorkerContext(
        container, Service, entrypoint, args=({'foo': 'bar'},)
    )


@pytest.fixture
def supported_workers(
    rpc_worker_ctx, http_worker_ctx, event_worker_ctx, consumer_worker_ctx
):
    return [
        rpc_worker_ctx, http_worker_ctx, event_worker_ctx, consumer_worker_ctx
    ]


@pytest.fixture
def dummy_worker_ctx(mock_container):
    mock_container.service_name = "service"
    return WorkerContext(mock_container, None, DummyProvider())


def test_setup(entrypoint_logger):
    assert EntrypointLoggingHandler in [
        type(handler) for handler in entrypoint_logger.logger.handlers
        if type(handler) == EntrypointLoggingHandler]

    assert EXCHANGE_NAME in str(entrypoint_logger.container.config)
    assert ROUTING_KEY in str(entrypoint_logger.container.config)


def test_missing_config(mock_container):
    mock_container.config = {}
    dependency_provider = EntrypointLogger().bind(mock_container, 'logger')

    with patch('nameko_entrypoint_logger.log') as log:
        dependency_provider.setup()

    calls = [call('EntrypointLogger is disabled')]
    assert calls == log.warning.call_args_list
    assert dependency_provider.logger is None


def test_disabled_by_config(mock_container, config):
    del config['ENTRYPOINT_LOGGING']['ENABLED']
    mock_container.config = config
    dependency_provider = EntrypointLogger().bind(mock_container, 'logger')

    with patch('nameko_entrypoint_logger.log') as log:
        dependency_provider.setup()

    calls = [call('EntrypointLogger is disabled')]
    assert calls == log.warning.call_args_list
    assert dependency_provider.logger is None


def test_disabled_by_config_explicitly(mock_container, config):
    config['ENTRYPOINT_LOGGING']['ENABLED'] = False
    mock_container.config = config
    dependency_provider = EntrypointLogger().bind(mock_container, 'logger')

    with patch('nameko_entrypoint_logger.log') as log:
        dependency_provider.setup()

    calls = [call('EntrypointLogger is disabled')]
    assert calls == log.warning.call_args_list
    assert dependency_provider.logger is None


@pytest.mark.parametrize('required_key', [
    'AMQP_URI',
    'EXCHANGE_NAME',
    'ROUTING_KEY',
])
def test_missing_config_key(required_key, config, mock_container):
    del config['ENTRYPOINT_LOGGING'][required_key]
    mock_container.config = config
    dependency_provider = EntrypointLogger().bind(mock_container, 'logger')

    with pytest.raises(ConfigurationError) as exc:
        dependency_provider.setup()
    assert "missing key `{}`".format(required_key) in str(exc.value)
    assert dependency_provider.logger is None


def test_will_not_process_request_from_unknown_entrypoints(
    entrypoint_logger, dummy_worker_ctx
):
    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_setup(dummy_worker_ctx)

    assert not logger.info.called


def test_will_not_process_results_from_unknown_entrypoints(
    entrypoint_logger, dummy_worker_ctx
):
    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(dummy_worker_ctx)

    assert not logger.info.called


def test_will_not_process_request_if_disabled(
    entrypoint_logger, rpc_worker_ctx
):
    with patch.object(entrypoint_logger, 'enabled', False):
        with patch.object(entrypoint_logger, 'logger') as logger:
            entrypoint_logger.worker_setup(rpc_worker_ctx)

    assert not logger.info.called


def test_will_not_process_results_if_disabled(
    entrypoint_logger, rpc_worker_ctx
):
    with patch.object(entrypoint_logger, 'enabled', False):
        with patch.object(entrypoint_logger, 'logger') as logger:
            entrypoint_logger.worker_result(rpc_worker_ctx)

    assert not logger.info.called


def test_requests_from_supported_workers_are_logged(
    entrypoint_logger, supported_workers
):
    with patch.object(entrypoint_logger, 'logger') as logger:
        with patch('nameko_entrypoint_logger.get_worker_data') as data:
            data.return_value = {'timestamp': datetime.utcnow()}
            for worker_ctx in supported_workers:
                entrypoint_logger.worker_setup(worker_ctx)
                (call_args,), _ = logger.info.call_args
                assert '"lifecycle_stage": "request"' in call_args

    assert logger.info.call_count == len(supported_workers)


def test_results_from_supported_workers_are_logged(
    entrypoint_logger, supported_workers
):
    with patch.object(entrypoint_logger, 'logger') as logger:
        with patch('nameko_entrypoint_logger.get_worker_data') as data:
            data.return_value = {'timestamp': datetime.utcnow()}
            with patch.object(
                entrypoint_logger, 'calculate_response_time'
            ) as response_time:
                response_time.return_value = 0.001
                for worker in supported_workers:
                    entrypoint_logger.worker_result(worker)
                    (call_args,), _ = logger.info.call_args
                    assert '"lifecycle_stage": "response"' in call_args

    assert logger.info.call_count == len(supported_workers)


def test_can_get_results_for_supported_workers(supported_workers):
    for worker in supported_workers:
        data = get_worker_data(worker)
        assert data['provider'] == type(worker.entrypoint).__name__
        assert data['hostname'] == socket.gethostname()
        assert data['service'] == worker.service_name
        assert data['provider_name'] == worker.entrypoint.method_name
        assert data['entrypoint'] == "{}.{}".format(
            data['service'], data['provider_name']
        )
        assert data['call_id'] == worker.call_id
        assert data['call_stack'] == worker.call_id_stack


def test_will_call_get_redacted_callargs(supported_workers):
    with patch('nameko_entrypoint_logger.get_redacted_args') as get_args:
        for worker in supported_workers:
            get_worker_data(worker)

    assert get_args.call_count == 2


def test_will_call_get_http_request(supported_workers):
    with patch('nameko_entrypoint_logger.get_http_request') as get_request:
        for worker in supported_workers:
            get_worker_data(worker)

    assert get_request.call_count == 1


def test_will_get_event_worker_redacted_callargs(event_worker_ctx):
    data = get_worker_data(event_worker_ctx)

    assert data['call_args'] == {
        'redacted_args': '{"payload": "bar"}'
    }


def test_will_get_rpc_worker_redacted_callargs(rpc_worker_ctx):
    data = get_worker_data(rpc_worker_ctx)

    assert data['call_args'] == {
        'redacted_args': '{"foo": "bar"}'
    }


@pytest.mark.parametrize(
    'result,result_serialized,result_bytes,status_code,content_type', [
        # can process dict result
        ({'foo': 'bar'}, '{"foo": "bar"}', 14, None, None),
        # can process string encoded dict result
        ("{'foo': 'bar'}", "{'foo': 'bar'}", 14, None, None),
        # can process string result
        ("foo=bar", 'foo=bar', 7, None, None),
        # can process None result
        (None, 'None', 4, None, None),
        # can process werkzeug's Response json result
        (Response(
            json.dumps({"value": 1}),
            mimetype='application/json'
        ), '{"value": 1}', 12, 200, 'application/json'),
        # can process werkzeug's Response text result
        (Response(
            "foo",
            mimetype='text/plain'
        ), 'foo', 3, 200, 'text/plain; charset=utf-8')
    ])
def test_can_process_results(
    result, result_serialized, result_bytes, status_code, content_type
):
    response = process_response(result)

    return_args = response['return_args']
    assert return_args['result'] == result_serialized
    assert return_args['result_bytes'] == result_bytes
    assert return_args['truncated'] is False
    if status_code is not None:
        assert return_args['status_code'] == status_code
    if content_type is not None:
        assert return_args['content_type'] == content_type


@pytest.mark.parametrize(
    'result', [
        {'foo': 'bar'},
        Response(json.dumps({'foo': 'bar'}), mimetype='application/json'),
    ]
)
def test_can_process_results_truncated(result):
    response = process_response(result, max_response_length=5)
    assert response['return_args']['result_bytes'] == 14
    assert response['return_args']['result'] == '{"foo'
    assert response['return_args']['truncated'] is True


@pytest.mark.parametrize('data,serialized_data,content_type', [
    (json.dumps({'foo': 'bar'}), '{"foo": "bar"}', 'application/json'),
    ('foo=bar', '{"foo": "bar"}', 'application/x-www-form-urlencoded'),
    ('foo=bar', 'foo=bar', 'text/plain')
])
def test_can_get_http_call_args(data, serialized_data, content_type):
    environ = create_environ(
        '/get/1?test=123',
        'http://localhost:8080/',
        data=data,
        content_type=content_type
    )

    request = Request(environ)

    request_call_args = get_http_request(request)
    assert request_call_args['data'] == serialized_data
    assert request_call_args['headers']['content_type'] == content_type


def test_entrypoint_logging_handler_will_publish_log_message():
    logger = logging.getLogger('test')
    handler = EntrypointLoggingHandler(publisher)
    logger.addHandler(handler)
    message = {'foo': 'bar'}
    logger.info(json.dumps(message))

    (call_args,), _ = publisher.call_args

    assert publisher.called
    assert json.loads(call_args) == message


def test_event_dispatcher_will_publish_logs(config):

    config = config.copy()
    config['ENTRYPOINT_LOGGING']['SERIALIZER'] = 'raw'
    config['ENTRYPOINT_LOGGING']['CONTENT_TYPE'] = 'binary'

    publisher = logging_publisher(config)

    message = {'foo': 'bar'}

    with patch('nameko_entrypoint_logger.producers') as mock_producers:
        with mock_producers[ANY].acquire(block=True) as mock_producer:
            publisher(json.dumps(message))

    (msg,), config = mock_producer.publish.call_args

    assert json.loads(msg) == message
    assert config['routing_key'] == ROUTING_KEY
    assert config['serializer'] == 'raw'
    assert config['content_type'] == 'binary'
    assert config['routing_key'] == ROUTING_KEY
    client = config['exchange'].channel.connection.client
    assert client.hostname == 'dev'
    assert client.transport_cls == 'memory'


def test_event_dispatcher_will_swallow_exception(config):
    publisher = logging_publisher(config)

    with patch('nameko_entrypoint_logger.log') as log:
        with patch('nameko_entrypoint_logger.producers') as producers:
            with producers[ANY].acquire(block=True) as producer:
                producer.publish.side_effect = BrokenPipeError(32, 'Oops')
                publisher({})

    assert log.error.called


def test_worker_setup_will_swallow_exceptions(
        entrypoint_logger, http_worker_ctx
):
    exception = Exception("Boom")
    with patch('nameko_entrypoint_logger.log') as log:
        with patch('nameko_entrypoint_logger.get_worker_data') as data:
            data.side_effect = exception
            entrypoint_logger.worker_setup(http_worker_ctx)

    assert [call(exception)] == log.error.call_args_list


def test_worker_results_will_swallow_exceptions(
        entrypoint_logger, http_worker_ctx
):
    exception = Exception("Boom")
    with patch('nameko_entrypoint_logger.log') as log:
        with patch('nameko_entrypoint_logger.get_worker_data') as data:
            data.side_effect = exception
            entrypoint_logger.worker_result(http_worker_ctx)

    assert [call(exception)] == log.error.call_args_list


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
    assert worker_data['exception']['expected_error'] is False
    assert worker_data['status'] == 'error'
    assert "Something went wrong" in str(worker_data['exception']['exc'])


def test_expected_exception_is_logged(entrypoint_logger, rpc_worker_ctx):
    exception = CustomException("Invalid value")
    exc_info = (CustomException, exception, exception.__traceback__)

    entrypoint_logger.worker_timestamps[rpc_worker_ctx] = datetime.utcnow()

    with patch.object(entrypoint_logger, 'logger') as logger:
        entrypoint_logger.worker_result(
            rpc_worker_ctx, result={'bar': 'foo'}, exc_info=exc_info
        )

    (call_args,), _ = logger.info.call_args

    worker_data = json.loads(call_args)

    assert worker_data['provider'] == "Rpc"
    assert worker_data['exception']['expected_error'] is True
    assert worker_data['status'] == 'error'
    assert "Invalid value" in str(worker_data['exception']['exc'])


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

    assert worker_data['exception']['exc'] == '[exc serialization failed]'


def test_end_to_end(container_factory, config):
    class TestService(object):
        name = "service"

        entrypoint_logger = EntrypointLogger()

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


def test_end_to_end_default_response_truncation(container_factory, config):
    class TestService(object):
        name = "service"

        entrypoint_logger = EntrypointLogger()

        @rpc
        def rpc_method(self):
            return 'A' * 200

        @rpc
        def get_rpc(self):
            return 'B' * 200

        @rpc
        def list_rpc(self):
            return 'C' * 200

        @rpc
        def query_rpc(self):
            return {'my_result': 'D' * 200}

    container = container_factory(TestService, config)
    container.start()

    logger = get_extension(container, EntrypointLogger)

    with patch.object(logger, 'logger') as logger:
        # invoke all the service methods
        for meth_name in ['rpc_method', 'get_rpc', 'list_rpc', 'query_rpc']:
            with entrypoint_hook(container, meth_name) as rpc_meth:
                with entrypoint_waiter(container, meth_name):
                    rpc_meth()

    def get_response_dict_from_log_call(log_call):
        return json.loads(log_call[0][0])

    assert logger.info.call_count == 8
    rpc_method_response = get_response_dict_from_log_call(
        logger.info.call_args_list[1])
    assert rpc_method_response['entrypoint'] == 'service.rpc_method'
    assert rpc_method_response['return_args']['result_bytes'] == 200
    assert rpc_method_response['return_args']['result'] == 'A' * 200
    assert rpc_method_response['return_args']['truncated'] is False

    get_rpc_response = get_response_dict_from_log_call(
        logger.info.call_args_list[3])
    assert get_rpc_response['entrypoint'] == 'service.get_rpc'
    assert get_rpc_response['return_args']['result_bytes'] == 200
    assert get_rpc_response['return_args']['result'] == 'B' * 100
    assert get_rpc_response['return_args']['truncated'] is True

    list_rpc_response = get_response_dict_from_log_call(
        logger.info.call_args_list[5])
    assert list_rpc_response['entrypoint'] == 'service.list_rpc'
    assert list_rpc_response['return_args']['result_bytes'] == 200
    assert list_rpc_response['return_args']['result'] == 'C' * 100
    assert list_rpc_response['return_args']['truncated'] is True

    query_rpc_response = get_response_dict_from_log_call(
        logger.info.call_args_list[7])
    assert query_rpc_response['entrypoint'] == 'service.query_rpc'
    assert query_rpc_response['return_args']['result_bytes'] == 217
    assert query_rpc_response['return_args']['result'] == (
        '{"my_result": "%s' % ('D' * 85)
    )
    assert query_rpc_response['return_args']['truncated'] is True


def test_end_to_end_custom_response_truncation(container_factory, config):
    class TestService(object):
        name = "service"

        entrypoint_logger = EntrypointLogger()

        @rpc
        def get_rpc1(self):
            return 'A' * 200

        @rpc
        def get_rpc2(self):
            return 'B' * 200

        @rpc
        def get_rpc3(self):
            return 'C' * 200

    custom_config = {}
    custom_config.update(config)
    custom_config['ENTRYPOINT_LOGGING']['TRUNCATED_RESPONSE_ENTRYPOINTS'] = [
        'get_rpc1', 'get_rpc3'
    ]

    container = container_factory(TestService, custom_config)
    container.start()

    logger = get_extension(container, EntrypointLogger)

    with patch.object(logger, 'logger') as logger:
        # invoke all the service methods
        for meth_name in ['get_rpc1', 'get_rpc2', 'get_rpc3']:
            with entrypoint_hook(container, meth_name) as rpc_meth:
                with entrypoint_waiter(container, meth_name):
                    rpc_meth()

    def get_response_dict_from_log_call(log_call):
        return json.loads(log_call[0][0])

    assert logger.info.call_count == 6
    get_rpc1_response = get_response_dict_from_log_call(
        logger.info.call_args_list[1])
    assert get_rpc1_response['entrypoint'] == 'service.get_rpc1'
    assert get_rpc1_response['return_args']['result_bytes'] == 200
    assert get_rpc1_response['return_args']['result'] == 'A' * 100
    assert get_rpc1_response['return_args']['truncated'] is True

    get_rpc2_response = get_response_dict_from_log_call(
        logger.info.call_args_list[3])
    assert get_rpc2_response['entrypoint'] == 'service.get_rpc2'
    assert get_rpc2_response['return_args']['result_bytes'] == 200
    assert get_rpc2_response['return_args']['result'] == 'B' * 200
    assert get_rpc2_response['return_args']['truncated'] is False

    get_rpc3_response = get_response_dict_from_log_call(
        logger.info.call_args_list[5])
    assert get_rpc3_response['entrypoint'] == 'service.get_rpc3'
    assert get_rpc3_response['return_args']['result_bytes'] == 200
    assert get_rpc3_response['return_args']['result'] == 'C' * 100
    assert get_rpc3_response['return_args']['truncated'] is True


@pytest.mark.parametrize(
    ('trunc_value', 'expected'), [
        (None, []),
        ([], []),
        ("", []),
        (['a', 'b'], [re.compile('a'), re.compile('b')]),
    ]
)
def test_truncated_response_config(
    mock_container, config, trunc_value, expected
):
    custom_config = {}
    custom_config.update(config)
    custom_config['ENTRYPOINT_LOGGING']['TRUNCATED_RESPONSE_ENTRYPOINTS'] = (
        trunc_value
    )
    mock_container.config = custom_config
    dependency_provider = EntrypointLogger().bind(mock_container, 'logger')
    dependency_provider.setup()
    assert dependency_provider.truncated_response_entrypoints == expected


def test_truncated_response_default_config(mock_container, config):
    assert 'TRUNCATED_RESPONSE_ENTRYPOINTS' not in config['ENTRYPOINT_LOGGING']

    mock_container.config = config
    dependency_provider = EntrypointLogger().bind(mock_container, 'logger')
    dependency_provider.setup()
    assert dependency_provider.truncated_response_entrypoints == [
        re.compile('^get_|^list_|^query_')
    ]


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


@pytest.mark.parametrize(
    ('truncated_entrypoints', 'expected'), [
        ([re.compile('foo')], False),
        ([re.compile('foo'), re.compile('rpc_method')], True),
        ([re.compile('rpc_method'), re.compile('foo')], True),
    ]
)
def test_should_truncate(rpc_worker_ctx, truncated_entrypoints, expected):
    result = should_truncate(rpc_worker_ctx, truncated_entrypoints)
    assert result == expected
