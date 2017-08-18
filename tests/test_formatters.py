from datetime import datetime
import json

from mock import Mock
import pytest

from nameko_tracer import constants, formatters


@pytest.mark.parametrize(
    ('input_', 'expected_output'),
    (
        (
            {'datetime': datetime(2017, 7, 7, 12, 0)},
            '{"datetime": "2017-07-07 12:00:00"}'
        ),
        ({None}, '"{None}"'),
    )
)
def test_json_serialiser_will_deal_with_datetime(input_, expected_output):

    log_record = Mock()
    setattr(log_record, constants.TRACE_KEY, input_)

    assert (
        formatters.JSONFormatter().format(log_record) == expected_output)


def test_elasticsearch_document_serialiser():

    trace = {
        constants.CONTEXT_DATA_KEY: {'should': ('be', 'serialised')},
        constants.REQUEST_KEY: ('should', 'be', 'serialised'),
        constants.RESPONSE_KEY: {'should': ('be', 'serialised')},
        'some-other-key': {'should': ['NOT', 'be', 'serialised']},
    }

    log_record = Mock()
    setattr(log_record, constants.TRACE_KEY, trace)

    document = formatters.ElasticisearchDocumentFormatter().format(log_record)

    document = json.loads(document)

    assert (
        document[constants.CONTEXT_DATA_KEY] ==
        '{"should": ["be", "serialised"]}')
    assert (
        document[constants.REQUEST_KEY] ==
        '["should", "be", "serialised"]')
    assert (
        document[constants.RESPONSE_KEY] ==
        '{"should": ["be", "serialised"]}')
    assert (
        document['some-other-key'] ==
        {'should': ['NOT', 'be', 'serialised']})
