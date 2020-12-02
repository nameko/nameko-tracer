import json
import logging
from functools import partial

from nameko_tracer import constants


def default(obj):
    return str(obj)


serialise = partial(json.dumps, default=default)


class JSONFormatter(logging.Formatter):
    """ Format trace data as JSON string
    """
    def __init__(self, **option):
        self.option = option

    def format(self, record):
        return serialise(getattr(record, constants.TRACE_KEY), **self.option)


PrettyJSONFormatter = partial(JSONFormatter, indent=4, sort_keys=True)


class ElasticsearchDocumentFormatter(JSONFormatter):
    """ Format trace as JSON which can be fed to Elasticsearch as a document

    Request and response data fields of the document are serialized as JSON
    string before serialising the whole output.

    """

    extra_serialise_keys = (
        constants.CONTEXT_DATA_KEY,
        constants.REQUEST_KEY,
        constants.RESPONSE_KEY,
        constants.EXCEPTION_ARGS_KEY)

    def format(self, record):

        trace = getattr(record, constants.TRACE_KEY)

        for key in self.extra_serialise_keys:
            if key in trace:
                trace[key] = serialise(trace[key])

        return serialise(trace)
