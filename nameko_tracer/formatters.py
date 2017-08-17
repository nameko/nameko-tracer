import json
import logging

from nameko_tracer import constants


def default(obj):
    return str(obj)


class JSONFormatter(logging.Formatter):

    def format(self, record):
        return json.dumps(
            getattr(record, constants.TRACE_KEY), default=default)
