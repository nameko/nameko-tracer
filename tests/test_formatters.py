import pytest

from nameko_entrypoint_logger.formatters import dumps


def test_default_json_serializer_will_raise_value_error():
    with pytest.raises(ValueError):
        dumps({'weird_value': {None}})
