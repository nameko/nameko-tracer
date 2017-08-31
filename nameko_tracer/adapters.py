import inspect
import logging
from traceback import format_exception

from nameko.exceptions import get_module_path
from nameko.utils import get_redacted_args
import six

from nameko_tracer import constants, utils


logger = logging.getLogger(__name__)


class DefaultAdapter(logging.LoggerAdapter):

    def process(self, message, kwargs):
        """ Extract useful entrypoint processing information

        Extract useful entrypoint information and set it as
        ``constants.TRACE_KEY`` named attribute of the log record.
        Content of this attribute should be easily serialisable and the aim
        is to fill it with something that can go easily over a wire and that
        can be easily stored, filtered and searched.

        """

        hostname = self.extra['hostname']

        stage = kwargs['extra']['stage']
        worker_ctx = kwargs['extra']['worker_ctx']
        timestamp = kwargs['extra']['timestamp']

        entrypoint = worker_ctx.entrypoint

        data = kwargs['extra'].get(constants.TRACE_KEY, {})

        data[constants.TIMESTAMP_KEY] = timestamp
        data[constants.HOSTNAME_KEY] = hostname
        data[constants.SERVICE_NAME_KEY] = worker_ctx.service_name
        data[constants.ENTRYPOINT_TYPE_KEY] = type(entrypoint).__name__
        data[constants.ENTRYPOINT_NAME_KEY] = entrypoint.method_name

        data[constants.CONTEXT_DATA_KEY] = utils.safe_for_serialisation(
            worker_ctx.data)

        data[constants.CALL_ID_KEY] = worker_ctx.call_id
        data[constants.CALL_ID_STACK_KEY] = worker_ctx.call_id_stack

        data[constants.STAGE_KEY] = stage.value

        call_args, call_args_redacted = self.get_call_args(worker_ctx)
        data[constants.REQUEST_KEY] = call_args
        data[constants.REQUEST_REDACTED_KEY] = call_args_redacted

        if stage == constants.Stage.response:

            exc_info = kwargs['extra']['exc_info_']

            if exc_info:
                data[constants.RESPONSE_STATUS_KEY] = (
                    constants.Status.error.value)
                self.set_exception(data, worker_ctx, exc_info)
            else:
                data[constants.RESPONSE_STATUS_KEY] = (
                    constants.Status.success.value)
                result = kwargs['extra']['result']
                data[constants.RESPONSE_KEY] = self.get_result(result)

            data[constants.RESPONSE_TIME_KEY] = (
                kwargs['extra']['response_time'])

        kwargs['extra'][constants.TRACE_KEY] = data

        return message, kwargs

    def get_call_args(self, worker_ctx):
        """ Return serialisable call arguments
        """

        entrypoint = worker_ctx.entrypoint

        if getattr(entrypoint, 'sensitive_variables', None):
            call_args = get_redacted_args(
                entrypoint, *worker_ctx.args, **worker_ctx.kwargs)
            redacted = True
        else:
            method = getattr(
                entrypoint.container.service_cls, entrypoint.method_name)
            call_args = inspect.getcallargs(
                method, None, *worker_ctx.args, **worker_ctx.kwargs)
            del call_args['self']
            redacted = False

        return call_args, redacted

    def get_result(self, result):
        """ Return serialisable result data
        """
        return utils.safe_for_serialisation(result)

    def set_exception(self, data, worker_ctx, exc_info):
        """ Set exception details as serialisable trace attributes
        """

        exc_type, exc, _ = exc_info

        expected_exceptions = getattr(
            worker_ctx.entrypoint, 'expected_exceptions', None)
        expected_exceptions = expected_exceptions or tuple()
        is_expected = isinstance(exc, expected_exceptions)

        try:
            exc_traceback = ''.join(format_exception(*exc_info))
        except Exception:
            exc_traceback = 'traceback serialisation failed'

        exc_args = utils.safe_for_serialisation(exc.args)

        data[constants.EXCEPTION_TYPE_KEY] = exc_type.__name__
        data[constants.EXCEPTION_PATH_KEY] = get_module_path(exc_type)
        data[constants.EXCEPTION_ARGS_KEY] = exc_args
        data[constants.EXCEPTION_VALUE_KEY] = utils.safe_for_serialisation(exc)
        data[constants.EXCEPTION_TRACEBACK_KEY] = exc_traceback
        data[constants.EXCEPTION_EXPECTED_KEY] = is_expected


class HttpRequestHandlerAdapter(DefaultAdapter):

    def get_call_args(self, worker_ctx):
        """ Transform request object to serialized dictionary
        """

        entrypoint = worker_ctx.entrypoint

        method = getattr(
            entrypoint.container.service_cls, entrypoint.method_name)
        call_args = inspect.getcallargs(
            method, None, *worker_ctx.args, **worker_ctx.kwargs)
        del call_args['self']

        request = call_args.pop('request')
        data = request.data or request.form
        call_args['request'] = {
            'url': request.url,
            'method': request.method,
            'data': utils.safe_for_serialisation(data),
            'headers': dict(self.get_headers(request.environ)),
            'env': dict(self.get_environ(request.environ)),
        }

        return call_args, False

    def get_result(self, result):
        """ Transform response object to serialisable dictionary
        """
        return {
            'content_type': result.content_type,
            'data': result.get_data(),
            'status_code': result.status_code,
            'content_length': result.content_length,
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
