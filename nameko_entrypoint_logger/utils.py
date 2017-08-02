from importlib import import_module
import json

import six


def to_string(value):
    if isinstance(value, six.string_types):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, bytes):
        return value.decode("utf-8")


def import_by_path(dotted_path):
    """
    Import a dotted module path and return the attribute/class designated by
    the last name in the path. Raise ImportError if the import failed.

    Borrowed from ``django.utils.module_loading.import_string``.

    """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError:
        raise ImportError(
            "{} doesn't look like a module path".format(dotted_path))

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError:
        raise ImportError(
            'Module "{}" does not define a "{}" attribute/class'
            .format(module_path, class_name))
