import json

import six


def to_string(value):
    if isinstance(value, six.string_types):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")
