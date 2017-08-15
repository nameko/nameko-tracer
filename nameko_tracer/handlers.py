import logging

from kombu.pools import connections, producers
from kombu import Connection, Exchange
from nameko.constants import DEFAULT_RETRY_POLICY


logger = logging.getLogger(__name__)


class PublisherHandler(logging.Handler):
    """ Legacy handler publishing message to Rabbit
    """
    def __init__(
        self, amqp_uri, exchange_name, routing_key,
        serializer=None, content_type=None
    ):
        self.publisher = publisher(
            amqp_uri, exchange_name, routing_key, serializer, content_type)
        super(PublisherHandler, self).__init__()

    def emit(self, log_record):
        self.publisher(self.format(log_record))


def publisher(amqp_uri, exchange_name, routing_key, serializer, content_type):
    serializer = serializer or 'json'
    content_type = content_type or 'application/json'

    def publish(message_payload):

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
        except Exception:
            logger.error('Failed to publish a log message', exc_info=True)

    return publish
