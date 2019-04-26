import json
from datetime import datetime

import pytest
from mock import Mock

from nameko_tracer import constants, formatters


@pytest.mark.parametrize(
    ("input_", "expected_output"),
    (
        (
            {"datetime": datetime(2017, 7, 7, 12, 0)},
            '{"datetime": "2017-07-07 12:00:00"}',
        ),
        ({None}, '"{None}"'),
    ),
)
def test_json_serialiser_will_deal_with_datetime(input_, expected_output):

    log_record = Mock()
    setattr(log_record, constants.TRACE_KEY, input_)

    assert formatters.JSONFormatter().format(log_record) == expected_output


@pytest.mark.parametrize(
    ("key", "value_in", "expected_value_out"),
    (
        (
            constants.CONTEXT_DATA_KEY,
            {"should": ("be", "serialised")},
            '{"should": ["be", "serialised"]}',
        ),
        (
            constants.REQUEST_KEY,
            ("should", "be", "serialised"),
            '["should", "be", "serialised"]',
        ),
        (
            constants.RESPONSE_KEY,
            {"should": ("be", "serialised")},
            '{"should": ["be", "serialised"]}',
        ),
        (
            constants.EXCEPTION_ARGS_KEY,
            {"should": ("be", "serialised")},
            '{"should": ["be", "serialised"]}',
        ),
        (
            "some-other-key",
            {"should": ["NOT", "be", "serialised"]},
            {"should": ["NOT", "be", "serialised"]},
        ),
    ),
)
def test_elasticsearch_document_serialiser(key, value_in, expected_value_out):

    trace = {key: value_in}

    log_record = Mock()
    setattr(log_record, constants.TRACE_KEY, trace)

    document = formatters.ElasticsearchDocumentFormatter().format(log_record)

    document = json.loads(document)

    assert document[key] == expected_value_out
