import logging
import re


from nameko_entrypoint_logger import constants, utils


class TruncateFilter(logging.Filter):

    default_entrypoints = []

    lifecycle_stage = NotImplemented

    def __init__(self, entrypoints=None, max_len=None):

        entrypoints = entrypoints or self.default_entrypoints
        self.entrypoints = [re.compile(r) for r in entrypoints]

        self.max_len = max_len or 100

    def filter(self, log_record):
        data = getattr(log_record, constants.RECORD_ATTR)
        lifecycle_stage = data.get(constants.STAGE_KEY)
        entrypoint_name = data.get(constants.ENTRYPOINT_NAME_KEY)
        if (
            lifecycle_stage == self.lifecycle_stage.value and
            any(regex.match(entrypoint_name) for regex in self.entrypoints)
        ):
            data = self._filter(data)
            setattr(log_record, constants.RECORD_ATTR, data)
        return log_record

    def _filter(self, data):
        return data


class TruncateRequestFilter(TruncateFilter):
    """ Truncate serialized call arguments

    If the truncation is applied, the call data is serialised to string
    beforehand.

    """

    default_entrypoints = []

    lifecycle_stage = constants.Stage.request

    def _filter(self, data):
        call_args = to_string(data[constants.REQUEST_KEY])
        length = len(call_args)
        if length > self.max_len:
            call_args = call_args[:self.max_len]
            truncated = True
        else:
            truncated = False
        data[constants.REQUEST_KEY] = call_args
        data[constants.REQUEST_TRUNCATED_KEY] = truncated
        data[constants.REQUEST_LENGTH_KEY] = length
        return data


class TruncateResponseFilter(TruncateFilter):
    """ Truncate serialized response data

    If the truncation is applied, the call data is serialised to string
    beforehand.

    """

    default_entrypoints = ['^get_|^list_|^query_']

    lifecycle_stage = constants.Stage.response

    def _filter(self, data):
        result = to_string(data[constants.RESPONSE_KEY])
        length = len(result)
        if length > self.max_len:
            result = result[:self.max_len]
            truncated = True
        else:
            truncated = False
        data[constants.RESPONSE_KEY] = result
        data[constants.RESPONSE_TRUNCATED_KEY] = truncated
        data[constants.RESPONSE_LENGTH_KEY] = length
        return data
