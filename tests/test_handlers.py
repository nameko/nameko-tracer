import json
import logging

from mock import ANY, call, patch

from nameko_entrypoint_logger.handlers import PublisherHandler


@patch('nameko_entrypoint_logger.handlers.connections')
@patch('nameko_entrypoint_logger.handlers.producers')
def test_handler_will_publish_log_message(producers, connections):

    amqp_uri = 'some:uri'
    exchange_name = 'someexchange'
    routing_key = 'some.routing.key'
    serializer = 'raw'
    content_type = 'binary'

    handler = PublisherHandler(
        amqp_uri=amqp_uri,
        exchange_name=exchange_name,
        routing_key=routing_key,
        serializer=serializer,
        content_type=content_type,
    )

    logger = logging.getLogger('test')
    logger.addHandler(handler)

    message = {'foo': 'bar'}

    with producers[ANY].acquire(block=True) as producer:
        logger.info(json.dumps(message))

    (msg,), config = producer.publish.call_args

    assert json.loads(msg) == message
    assert config['routing_key'] == routing_key
    assert config['serializer'] == serializer
    assert config['content_type'] == content_type


@patch('nameko_entrypoint_logger.handlers.logger')
@patch('nameko_entrypoint_logger.handlers.connections')
@patch('nameko_entrypoint_logger.handlers.producers')
def test_handler_will_fial_with_logging_the_error(
    producers, connections, module_logger
):

    amqp_uri = 'some:uri'
    exchange_name = 'someexchange'
    routing_key = 'some.routing.key'

    handler = PublisherHandler(
        amqp_uri=amqp_uri,
        exchange_name=exchange_name,
        routing_key=routing_key,
    )

    connections[ANY].acquire.side_effect = Exception('Yo!')

    logger = logging.getLogger('test')
    logger.addHandler(handler)

    message = {'foo': 'bar'}

    logger.info(json.dumps(message))

    assert (
        module_logger.error.call_args ==
        call('Failed to publish a log message', exc_info=True))
