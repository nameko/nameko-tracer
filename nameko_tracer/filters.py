import abc
import logging
import re


from nameko_tracer import constants, utils


class BaseTruncateFilter(logging.Filter, abc.ABC):

    default_entrypoints = []

    lifecycle_stage = None

    def __init__(self, entrypoints=None, max_len=None):

        entrypoints = entrypoints or self.default_entrypoints
        self.entrypoints = [re.compile(r) for r in entrypoints]

        self.max_len = max_len or 100

    def filter(self, log_record):
        data = getattr(log_record, constants.TRACE_KEY)
        lifecycle_stage = data.get(constants.STAGE_KEY)
        entrypoint_name = data.get(constants.ENTRYPOINT_NAME_KEY)
        if (
            lifecycle_stage == self.lifecycle_stage.value and
            any(regex.match(entrypoint_name) for regex in self.entrypoints)
        ):
            data = self.truncate(data)
            setattr(log_record, constants.TRACE_KEY, data)
        return log_record

    @abc.abstractmethod
    def truncate(self, data):
        """ Truncate and return the data
        """


class TruncateRequestFilter(BaseTruncateFilter):
    """ Truncate serialized call arguments

    If the truncation is applied, the call data is serialised to string
    beforehand.

    Example of a filter truncating call arguments of entrypoint methods
    starting with "create" or "insert" to the length of 200 characters::

        filter = TruncateRequestFilter(
            entrypoints=['^create|^insert'], max_len=200)

    """

    default_entrypoints = []

    lifecycle_stage = constants.Stage.request

    def truncate(self, data):
        call_args = utils.serialise_to_string(data[constants.REQUEST_KEY])
        length = len(call_args)
        if length > self.max_len:
            data[constants.REQUEST_KEY] = call_args[:self.max_len]
            truncated = True
        else:
            truncated = False
        data[constants.REQUEST_TRUNCATED_KEY] = truncated
        data[constants.REQUEST_LENGTH_KEY] = length
        return data


class TruncateResponseFilter(BaseTruncateFilter):
    """ Truncate serialized response data

    If the truncation is applied, the call data is serialised to string
    beforehand.

    Example of a filter truncating return value of entrypoint methods
    starting with "get" or "list" to the length of 200 characters::

        filter = TruncateResponseFilter(
            entrypoints=['^get|^list'], max_len=200)

    """

    default_entrypoints = ['^get_|^list_|^query_']

    lifecycle_stage = constants.Stage.response

    def truncate(self, data):

        if constants.RESPONSE_KEY not in data:
            return data

        result = utils.serialise_to_string(data[constants.RESPONSE_KEY])
        length = len(result)
        if length > self.max_len:
            data[constants.RESPONSE_KEY] = result[:self.max_len]
            truncated = True
        else:
            truncated = False
        data[constants.RESPONSE_TRUNCATED_KEY] = truncated
        data[constants.RESPONSE_LENGTH_KEY] = length
        return data
