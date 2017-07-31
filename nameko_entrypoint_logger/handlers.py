import logging

from kombu.pools import connections, producers
from kombu import Connection, Exchange
from nameko.constants import DEFAULT_RETRY_POLICY


log = logging.getLogger(__name__)


class PublisherHandler(logging.Handler):
    def __init__(self, publisher):
        self.publisher = publisher
        super(PublisherHandler, self).__init__()

    def emit(self, message):
        self.publisher(message.getMessage())


def logging_publisher(config):
    """ Return a function that publishes AMQP messages.

    :Parameters:
        config: dict
            Entrypoint logger configuration
        exchange_name: str
            Exchange where messages should be published to
        routing_key: str
            Message routing key
    """

    def publish(message_payload):
        """ Publish message

        :Parameters:
            message_payload: dict
                message payload
        """
        entrypoint_logging_config = config['ENTRYPOINT_LOGGING']

        amqp_uri = entrypoint_logging_config['AMQP_URI']
        exchange_name = entrypoint_logging_config['EXCHANGE_NAME']
        routing_key = entrypoint_logging_config['ROUTING_KEY']

        serializer = entrypoint_logging_config.get(
            'SERIALIZER', 'json')

        content_type = entrypoint_logging_config.get(
            'CONTENT_TYPE', 'application/json')

        conn = Connection(amqp_uri)
        exchange = Exchange(exchange_name)

        try:

            with connections[conn].acquire(block=True) as connection:
                exchange.maybe_bind(connection)
                with producers[conn].acquire(block=True) as producer:
                    msg = message_payload
                    producer.publish(
                        msg,
                        exchange=exchange,
                        declare=[exchange],
                        serializer=serializer,
                        routing_key=routing_key,
                        retry=True,
                        retry_policy=DEFAULT_RETRY_POLICY,
                        content_type=content_type
                    )
        except Exception as exc:
            log.error(exc)

    return publish
