from datetime import datetime
import json
import logging

from nameko_entrypoint_logger import constants


def default(obj):
    """ Default JSON serializer.

    :param obj:
        Might be a datetime

    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise ValueError


def dumps(obj):
    return json.dumps(obj, default=default)


class JSONFormatter(logging.Formatter):

    def format(self, record):
        return dumps(getattr(record, constants.TRACE_KEY))
