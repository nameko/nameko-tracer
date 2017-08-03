from datetime import datetime

from mock import Mock
import pytest

from nameko_entrypoint_logger import constants, formatters


def test_json_serializer_will_deal_with_datetime():

    log_record = Mock()
    setattr(
        log_record,
        constants.RECORD_ATTR,
        {'datetime': datetime(2017, 7, 7, 12, 0)})

    assert (
        formatters.JSONFormatter().format(log_record) ==
        '{"datetime": "2017-07-07T12:00:00"}')


def test_json_serializer_will_raise_value_error():

    log_record = Mock()
    setattr(log_record, constants.RECORD_ATTR, {'weird_value': {None}})

    with pytest.raises(ValueError):
        formatters.JSONFormatter().format(log_record)
