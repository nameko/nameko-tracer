import logging

import pytest

from nameko_entrypoint_logger import constants, filters


@pytest.fixture
def handler():

    class LRUTracker(logging.Handler):

        def __init__(self, *args, **kwargs):
            self.log_record = None
            super(LRUTracker, self).__init__(*args, **kwargs)

        def emit(self, log_record):
            self.log_record = log_record

    return LRUTracker()


@pytest.yield_fixture
def logger(handler):
    logger = logging.getLogger('test')
    logger.addHandler(handler)
    yield logger
    for handller in logger.handlers:
        logger.removeHandler(handler)
    for filter_ in logger.filters:
        logger.removeFilter(filter_)


@pytest.mark.parametrize(
    (
        'entrypoints', 'max_len', 'expected_request',
        'expected_request_length', 'truncated',
    ),
    (
        (['spam'], 5, '12345', 9, True),
        (['^ham|spam'], 5, '12345', 9, True),
        (['^spam'], 5, '12345', 9, True),
        (['^spam'], 10, '123456789', 9, False),
        (['^ham'], 5, '123456789', None, False),
        (None, 5, '123456789', None, False),
        ([], 5, '123456789', None, False),
        ('', 5, '123456789', None, False),
    )
)
def test_truncate_request(
    handler, logger, entrypoints, max_len, expected_request,
    expected_request_length, truncated
):

    filter_ = filters.TruncateRequestFilter(
        entrypoints=entrypoints, max_len=max_len)

    logger.addFilter(filter_)

    extra = {
        constants.RECORD_ATTR: {
            constants.STAGE_KEY: constants.Stage.request.value,
            constants.ENTRYPOINT_NAME_KEY: 'spam',
            constants.REQUEST_KEY: '123456789',
        },
    }

    logger.info('request', extra=extra)

    data = getattr(handler.log_record, constants.RECORD_ATTR)

    assert data[constants.REQUEST_KEY] == expected_request
    assert data.get(constants.REQUEST_TRUNCATED_KEY, False) == truncated
    assert data.get(constants.REQUEST_LENGTH_KEY) == expected_request_length


@pytest.mark.parametrize(
    (
        'entrypoints', 'max_len', 'expected_response',
        'expected_response_length', 'truncated'
    ),
    (
        (['spam'], 5, '12345', 9, True),
        (['^ham|spam'], 5, '12345', 9, True),
        (['^spam'], 5, '12345', 9, True),
        (['^spam'], 10, '123456789', 9, False),
        (['^ham'], 5, '123456789', None, False),
        (None, 5, '123456789', None, False),
        ([], 5, '123456789', None, False),
        ('', 5, '123456789', None, False),
    )
)
def test_truncate_response(
    handler, logger, entrypoints, max_len, expected_response,
    expected_response_length, truncated
):

    filter_ = filters.TruncateResponseFilter(
        entrypoints=entrypoints, max_len=max_len)

    logger.addFilter(filter_)

    extra = {
        constants.RECORD_ATTR: {
            constants.STAGE_KEY: constants.Stage.response.value,
            constants.ENTRYPOINT_NAME_KEY: 'spam',
            constants.RESPONSE_KEY: '123456789',
        },
    }

    logger.info('response', extra=extra)

    data = getattr(handler.log_record, constants.RECORD_ATTR)

    assert data[constants.RESPONSE_KEY] == expected_response
    assert data.get(constants.RESPONSE_TRUNCATED_KEY, False) == truncated
    assert data.get(constants.RESPONSE_LENGTH_KEY) == expected_response_length


def test_truncate_request_ignores_response_data(handler, logger):

    filter_ = filters.TruncateRequestFilter(entrypoints=['^spam'], max_len=5)

    logger.addFilter(filter_)

    extra = {
        constants.RECORD_ATTR: {
            constants.STAGE_KEY: constants.Stage.response.value,
            constants.ENTRYPOINT_NAME_KEY: 'spam',
            constants.RESPONSE_KEY: '123456789',
        },
    }

    logger.info('response', extra=extra)

    data = getattr(handler.log_record, constants.RECORD_ATTR)

    assert data[constants.RESPONSE_KEY] == '123456789'
    assert constants.REQUEST_TRUNCATED_KEY not in data
    assert constants.REQUEST_LENGTH_KEY not in data
    assert constants.RESPONSE_TRUNCATED_KEY not in data
    assert constants.RESPONSE_LENGTH_KEY not in data


def test_truncate_response_ignores_request_data(handler, logger):

    filter_ = filters.TruncateResponseFilter(entrypoints=['^spam'], max_len=5)

    logger.addFilter(filter_)

    extra = {
        constants.RECORD_ATTR: {
            constants.STAGE_KEY: constants.Stage.request.value,
            constants.ENTRYPOINT_NAME_KEY: 'spam',
            constants.REQUEST_KEY: '123456789',
        },
    }

    logger.info('request', extra=extra)

    data = getattr(handler.log_record, constants.RECORD_ATTR)

    assert data[constants.REQUEST_KEY] == '123456789'
    assert constants.RESPONSE_TRUNCATED_KEY not in data
    assert constants.RESPONSE_LENGTH_KEY not in data
    assert constants.REQUEST_TRUNCATED_KEY not in data
    assert constants.REQUEST_LENGTH_KEY not in data


def test_base_truncate_filter_cannot_be_used(handler, logger):
    with pytest.raises(TypeError):
        filters.BaseTruncateFilter(entrypoints=['^spam'], max_len=5)
