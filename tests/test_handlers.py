import json
import logging

from mock import MagicMock

from nameko_entrypoint_logger.handlers import PublisherHandler


publisher = MagicMock()


def test_entrypoint_logging_handler_will_publish_log_message():
    logger = logging.getLogger('test')
    handler = PublisherHandler(publisher)
    logger.addHandler(handler)
    message = {'foo': 'bar'}
    logger.info(json.dumps(message))

    (call_args,), _ = publisher.call_args

    assert publisher.called
    assert json.loads(call_args) == message
