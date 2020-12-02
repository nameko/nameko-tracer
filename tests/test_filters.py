import logging
from unittest.mock import Mock

import pytest

from nameko_tracer import constants, filters


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
    logger = logging.getLogger("test")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    yield logger
    for handler in logger.handlers:
        logger.removeHandler(handler)
    for filter_ in logger.filters:
        logger.removeFilter(filter_)


@pytest.mark.parametrize(
    (
        "entrypoints",
        "max_len",
        "expected_request",
        "expected_request_length",
        "truncated",
        "stage",
    ),
    (
        # should truncate call args of 'spam' entrypoint
        (["spam"], 5, "12345", 9, True, constants.Stage.request),
        (["^ham|spam"], 5, "12345", 9, True, constants.Stage.request),
        (["^spam"], 5, "12345", 9, True, constants.Stage.request),
        (["^spam"], 5, "12345", 9, True, constants.Stage.response),
        # call args of 'spam' entrypoint shorter than max len
        (["^spam"], 10, "123456789", 9, False, constants.Stage.request),
        # 'spam' entrypoint does not match the regexp
        (["^ham"], 5, "123456789", None, False, constants.Stage.request),
        # no entrypoint should be truncated
        (None, 5, "123456789", None, False, constants.Stage.request),
        ([], 5, "123456789", None, False, constants.Stage.request),
        ("", 5, "123456789", None, False, constants.Stage.request),
    ),
)
def test_truncate_call_args(
    handler,
    logger,
    entrypoints,
    max_len,
    expected_request,
    expected_request_length,
    truncated,
    stage,
):

    filter_ = filters.TruncateCallArgsFilter(entrypoints=entrypoints, max_len=max_len)

    logger.addFilter(filter_)

    extra = {
        constants.TRACE_KEY: {
            constants.STAGE_KEY: stage.value,
            constants.ENTRYPOINT_NAME_KEY: "spam",
            constants.REQUEST_KEY: "123456789",
        },
    }

    logger.info("request", extra=extra)

    data = getattr(handler.log_record, constants.TRACE_KEY)

    assert data[constants.REQUEST_KEY] == expected_request
    assert data.get(constants.REQUEST_TRUNCATED_KEY, False) == truncated
    assert data.get(constants.REQUEST_LENGTH_KEY) == expected_request_length


def test_truncate_no_call_args(handler, logger):

    filter_ = filters.TruncateCallArgsFilter(entrypoints=["spam"], max_len=5)

    logger.addFilter(filter_)

    extra = {
        constants.TRACE_KEY: {
            constants.STAGE_KEY: constants.Stage.request,
            constants.ENTRYPOINT_NAME_KEY: "spam",
        },
    }

    logger.info("request", extra=extra)

    data = getattr(handler.log_record, constants.TRACE_KEY)
    assert data[constants.ENTRYPOINT_NAME_KEY] == "spam"
    assert constants.REQUEST_KEY not in data
    assert constants.REQUEST_TRUNCATED_KEY not in data
    assert constants.REQUEST_LENGTH_KEY not in data


@pytest.mark.parametrize(
    ("request_in", "expected_request_out"),
    (
        (
            ["too", "short"],
            ["too", "short"],  # untouched
        ),
        (
            "a long string should stay a string",
            "a long string should sta",
        ),
        (
            {"a": ("more", "complex", "data", "structure")},
            "{'a': ['more', 'complex'",  # turned to string
        ),
    ),
)
def test_truncate_call_args_to_string_casting(
    handler, logger, request_in, expected_request_out
):

    filter_ = filters.TruncateCallArgsFilter(entrypoints=["spam"], max_len=24)

    logger.addFilter(filter_)

    extra = {
        constants.TRACE_KEY: {
            constants.STAGE_KEY: constants.Stage.request.value,
            constants.ENTRYPOINT_NAME_KEY: "spam",
            constants.REQUEST_KEY: request_in,
        },
    }

    logger.info("request", extra=extra)

    data = getattr(handler.log_record, constants.TRACE_KEY)

    assert data[constants.REQUEST_KEY] == expected_request_out


@pytest.mark.parametrize(
    (
        "entrypoints",
        "max_len",
        "expected_response",
        "expected_response_length",
        "truncated",
    ),
    (
        # should truncate return value of 'spam' entrypoint
        (["spam"], 5, "12345", 9, True),
        (["^ham|spam"], 5, "12345", 9, True),
        (["^spam"], 5, "12345", 9, True),
        # return value of 'spam' entrypoint shorter than max len
        (["^spam"], 10, "123456789", 9, False),
        # 'spam' entrypoint does not match the regexp
        (["^ham"], 5, "123456789", None, False),
        # no entrypoint should be truncated
        (None, 5, "123456789", None, False),
        ([], 5, "123456789", None, False),
        ("", 5, "123456789", None, False),
    ),
)
def test_truncate_response(
    handler,
    logger,
    entrypoints,
    max_len,
    expected_response,
    expected_response_length,
    truncated,
):

    filter_ = filters.TruncateResponseFilter(entrypoints=entrypoints, max_len=max_len)

    logger.addFilter(filter_)

    extra = {
        constants.TRACE_KEY: {
            constants.STAGE_KEY: constants.Stage.response.value,
            constants.ENTRYPOINT_NAME_KEY: "spam",
            constants.RESPONSE_KEY: "123456789",
        },
    }

    logger.info("response", extra=extra)

    data = getattr(handler.log_record, constants.TRACE_KEY)

    assert data[constants.RESPONSE_KEY] == expected_response
    assert data.get(constants.RESPONSE_TRUNCATED_KEY, False) == truncated
    assert data.get(constants.RESPONSE_LENGTH_KEY) == expected_response_length


@pytest.mark.parametrize(
    ("response_in", "expected_response_out"),
    (
        (
            ["too", "short"],
            ["too", "short"],  # untouched
        ),
        (
            "a long string should stay a string",
            "a long string should sta",
        ),
        (
            {"a": ("more", "complex", "data", "structure")},
            "{'a': ['more', 'complex'",  # turned to string
        ),
    ),
)
def test_truncate_response_to_string_casting(
    handler, logger, response_in, expected_response_out
):

    filter_ = filters.TruncateResponseFilter(entrypoints=["spam"], max_len=24)

    logger.addFilter(filter_)

    extra = {
        constants.TRACE_KEY: {
            constants.STAGE_KEY: constants.Stage.response.value,
            constants.ENTRYPOINT_NAME_KEY: "spam",
            constants.RESPONSE_KEY: response_in,
        },
    }

    logger.info("response", extra=extra)

    data = getattr(handler.log_record, constants.TRACE_KEY)

    assert data[constants.RESPONSE_KEY] == expected_response_out


def test_truncate_response_ignores_error_response(handler, logger):

    filter_ = filters.TruncateResponseFilter(entrypoints=["^spam"], max_len=5)

    logger.addFilter(filter_)

    extra = {
        constants.TRACE_KEY: {
            constants.STAGE_KEY: constants.Stage.response.value,
            constants.ENTRYPOINT_NAME_KEY: "spam",
            constants.RESPONSE_STATUS_KEY: constants.Status.error.value,
        },
    }

    logger.info("response", extra=extra)

    data = getattr(handler.log_record, constants.TRACE_KEY)

    assert constants.RESPONSE_TRUNCATED_KEY not in data
    assert constants.RESPONSE_LENGTH_KEY not in data
    assert constants.REQUEST_TRUNCATED_KEY not in data
    assert constants.REQUEST_LENGTH_KEY not in data


def test_truncate_request_ignores_response_data(handler, logger):

    filter_ = filters.TruncateCallArgsFilter(entrypoints=["^spam"], max_len=5)

    logger.addFilter(filter_)

    extra = {
        constants.TRACE_KEY: {
            constants.STAGE_KEY: constants.Stage.response.value,
            constants.ENTRYPOINT_NAME_KEY: "spam",
            constants.RESPONSE_KEY: "123456789",
        },
    }

    logger.info("response", extra=extra)

    data = getattr(handler.log_record, constants.TRACE_KEY)

    assert data[constants.RESPONSE_KEY] == "123456789"
    assert constants.REQUEST_TRUNCATED_KEY not in data
    assert constants.REQUEST_LENGTH_KEY not in data
    assert constants.RESPONSE_TRUNCATED_KEY not in data
    assert constants.RESPONSE_LENGTH_KEY not in data


def test_truncate_response_ignores_request_data(handler, logger):

    filter_ = filters.TruncateResponseFilter(entrypoints=["^spam"], max_len=5)

    logger.addFilter(filter_)

    extra = {
        constants.TRACE_KEY: {
            constants.STAGE_KEY: constants.Stage.request.value,
            constants.ENTRYPOINT_NAME_KEY: "spam",
            constants.REQUEST_KEY: "123456789",
        },
    }

    logger.info("request", extra=extra)

    data = getattr(handler.log_record, constants.TRACE_KEY)

    assert data[constants.REQUEST_KEY] == "123456789"
    assert constants.RESPONSE_TRUNCATED_KEY not in data
    assert constants.RESPONSE_LENGTH_KEY not in data
    assert constants.REQUEST_TRUNCATED_KEY not in data
    assert constants.REQUEST_LENGTH_KEY not in data


def test_base_truncate_filter_cannot_be_used(handler, logger):
    with pytest.raises(TypeError):
        filters.BaseTruncateFilter(entrypoints=["^spam"], max_len=5)


@pytest.mark.parametrize(
    ("log_record", "should_log"),
    (
        # not an HTTP entrypoint
        (object(), True),
        # HTTP entrypoint, log any url ...
        (Mock(**{"worker_ctx.entrypoint.url": "/some/url"}), True),
        # ... except the health check one
        (Mock(**{"worker_ctx.entrypoint.url": "/healthcheck"}), False),
        (Mock(**{"worker_ctx.entrypoint.url": "/health-check"}), False),
        (Mock(**{"worker_ctx.entrypoint.url": "/health_check"}), False),
    ),
)
def test_health_check_filter(log_record, should_log):
    filter_ = filters.HealthCheckTraceFilter()
    assert filter_.filter(log_record) == should_log
