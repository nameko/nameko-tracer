import json
import logging

from nameko_tracer import constants


def default(obj):
    return str(obj)


def serialise(obj):
    return json.dumps(obj, default=default)


class JSONFormatter(logging.Formatter):
    """ Format trace data as JSON string
    """

    def format(self, record):
        return serialise(getattr(record, constants.TRACE_KEY))


class ElasticsearchDocumentFormatter(JSONFormatter):
    """ Format trace as JSON which can be fed to Elasticsearch as a document

    Request and response data fields of the document are serialized as JSON
    string before serialising the whole output.

    """

    def format(self, record):
        trace = getattr(record, constants.TRACE_KEY)
        trace[constants.CONTEXT_DATA_KEY] = serialise(
            trace[constants.CONTEXT_DATA_KEY])
        trace[constants.REQUEST_KEY] = serialise(
            trace[constants.REQUEST_KEY])
        trace[constants.RESPONSE_KEY] = serialise(
            trace[constants.RESPONSE_KEY])
        return serialise(trace)
