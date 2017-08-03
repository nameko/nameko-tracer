import inspect
import logging
from traceback import format_exception

from nameko.constants import (
    LANGUAGE_CONTEXT_KEY,
    USER_AGENT_CONTEXT_KEY,
    USER_ID_CONTEXT_KEY,
)
from nameko.exceptions import safe_for_serialization, serialize
from nameko.utils import get_redacted_args
import six

from nameko_entrypoint_logger import constants, utils


logger = logging.getLogger(__name__)


class EntrypointAdapter(logging.LoggerAdapter):

    def process(self, message, kwargs):
        """ Extract useful entrypoint processing information

        Extract useful entrypoint information and set it as
        ``constants.RECORD_ATTR`` named attribute of the log record.
        Content of this attribute should be easily serialisable and the aim
        is to fill it with something that can go easily over a wire and that
        can be easily stored, filtered and searched.

        """

        stage = kwargs['extra']['stage']
        worker_ctx = kwargs['extra']['worker_ctx']
        timestamp = kwargs['extra']['timestamp']

        entrypoint = worker_ctx.entrypoint

        data = kwargs['extra'].get(constants.RECORD_ATTR, {})

        data[constants.TIMESTAMP_KEY] = timestamp
        data[constants.SERVICE_NAME_KEY] = worker_ctx.service_name
        data[constants.ENTRYPOINT_TYPE_KEY] = type(entrypoint).__name__
        data[constants.ENTRYPOINT_NAME_KEY] = entrypoint.method_name
        data[constants.ENTRYPOINT_PATH_KEY] = '{}.{}'.format(
                worker_ctx.service_name, entrypoint.method_name)

        data['context_data'] = {
            LANGUAGE_CONTEXT_KEY: worker_ctx.data.get(
                LANGUAGE_CONTEXT_KEY),
            USER_AGENT_CONTEXT_KEY: worker_ctx.data.get(
                USER_AGENT_CONTEXT_KEY),
            USER_ID_CONTEXT_KEY: worker_ctx.data.get(
                USER_ID_CONTEXT_KEY),
        }

        data[constants.CALL_ID_KEY] = worker_ctx.call_id
        data[constants.CALL_ID_STACK_KEY] = worker_ctx.call_id_stack

        data[constants.STAGE_KEY] = stage.value

        call_args, call_args_redacted = self.get_call_args(worker_ctx)
        data[constants.REQUEST_KEY] = call_args
        data[constants.REQUEST_REDUCTED_KEY] = call_args_redacted

        if stage == constants.Stage.response:

            exc_info = kwargs['extra']['exc_info_']

            if exc_info:
                data[constants.RESPONSE_STATUS_KEY] = (
                    constants.Status.error.value)
                data[constants.ERROR_KEY] = self.get_error(
                    worker_ctx, exc_info)
            else:
                data[constants.RESPONSE_STATUS_KEY] = (
                    constants.Status.success.value)
                result = kwargs['extra']['result']
                data[constants.RESPONSE_KEY] = self.get_result(result)

            data[constants.RESPONSE_TIME_KEY] = (
                kwargs['extra']['response_time'])

        kwargs['extra'][constants.RECORD_ATTR] = data

        return message, kwargs

    def get_call_args(self, worker_ctx):
        """ Return serialisable call arguments
        """

        provider = worker_ctx.entrypoint

        if getattr(provider, 'sensitive_variables', None):
            call_args = get_redacted_args(
                provider, *worker_ctx.args, **worker_ctx.kwargs)
            redacted = True
        else:
            method = getattr(
                provider.container.service_cls, provider.method_name)
            call_args = inspect.getcallargs(
                method, None, *worker_ctx.args, **worker_ctx.kwargs)
            del call_args['self']
            redacted = False

        return call_args, redacted

    def get_result(self, result):
        """ Return serialisable result data
        """
        return safe_for_serialization(result)

    def get_error(self, worker_ctx, exc_info):
        """ Transform exception to serialisable dictionary
        """

        expected_exceptions = getattr(
            worker_ctx.entrypoint, 'expected_exceptions', None)
        expected_exceptions = expected_exceptions or tuple()

        exc = exc_info[1]
        is_expected = isinstance(exc, expected_exceptions)

        try:
            exc_repr = serialize(exc)
        except Exception:
            exc_repr = 'exception serialization failed'

        try:
            exc_traceback = ''.join(format_exception(*exc_info))
        except Exception:
            exc_traceback = 'traceback serialization failed'

        return {
            'exc_type': exc_info[0].__name__,
            'exc': utils.to_string(exc_repr),
            'traceback': exc_traceback,
            'expected_error': is_expected,
        }


class HttpRequestHandlerAdapter(EntrypointAdapter):

    def get_call_args(self, worker_ctx):
        """ Transform request object to serialized dictionary
        """

        # TODO: HttpRequestHandler should support sensitive_variables

        provider = worker_ctx.entrypoint

        method = getattr(
            provider.container.service_cls, provider.method_name)
        call_args = inspect.getcallargs(
            method, None, *worker_ctx.args, **worker_ctx.kwargs)
        del call_args['self']

        request = call_args.pop('request')
        data = request.data or request.form
        call_args['request'] = {
            'url': request.url,
            'method': request.method,
            'data': utils.to_string(data),
            'headers': dict(self.get_headers(request.environ)),
            'env': dict(self.get_environ(request.environ)),
        }

        return call_args, False

    def get_result(self, result):
        """ Transform response object to serialisable dictionary
        """
        return {
            'content_type': result.content_type,
            'result': result.get_data(),
            'status_code': result.status_code,
            'result_bytes': result.content_length,
        }

    def get_headers(self, environ):
        """ Return only proper HTTP headers
        """
        for key, value in six.iteritems(environ):
            key = str(key)
            if key.startswith('HTTP_') and key not in \
                    ('HTTP_CONTENT_TYPE', 'HTTP_CONTENT_LENGTH'):
                yield key[5:].lower(), str(value)
            elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                yield key.lower(), str(value)

    def get_environ(self, environ):
        """ Return white-listed environment variables
        """
        for key in ('REMOTE_ADDR', 'SERVER_NAME', 'SERVER_PORT'):
            if key in environ:
                yield key.lower(), str(environ[key])
