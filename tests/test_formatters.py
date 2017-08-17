from datetime import datetime

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
def test_json_serializer_will_deal_with_datetime(input_, expected_output):

    log_record = Mock()
    setattr(log_record, constants.TRACE_KEY, input_)

    assert (
        formatters.JSONFormatter().format(log_record) == expected_output)
