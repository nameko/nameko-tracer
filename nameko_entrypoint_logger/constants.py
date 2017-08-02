from enum import Enum


class Stage(Enum):
    request = 'request'
    response = 'response'


class Status(Enum):
    success = 'success'
    error = 'error'


LOGGER_NAME = 'entrypoint_logger'
""" Name of the logger used for entrypoint logging

Use this name to configure entrypoint logging in ``LOGGING`` setting
of Nameko config.

"""

RECORD_ATTR = 'data'
""" Name of the log record attribute the gathered entrypoint data is set to

...

"""


TIMESTAMP_KEY = 'timestamp'


STAGE_KEY = 'lifecycle_stage'


HOSTNAME_KEY = 'hostname'


REQUEST_KEY = 'call_args'
""" Entrypoint call arguments key

A key holding serialized tuple of args and kwargs passed to the entrypoint
call.

"""

REQUEST_REDUCTED_KEY = 'call_args_reducted'

RESPONSE_KEY = 'return_args'
""" Entrypoint return key

A key holding serialized return value of the entrypoint.

"""

REQUEST_TRUNCATED_KEY = 'call_args_truncated'
""" Set to ``True`` if the request data were truncated

Set by ``TruncateRequestFilter`` if the data in ``REQUEST_KEY`` were
truncated by the filter.

"""

RESPONSE_TRUNCATED_KEY = 'return_args_truncated'
""" Set to ``True`` if the response data were truncated

Set by ``TruncateResponseFilter`` if the data in ``RESPONSE_KEY`` were
truncated by the filter.

"""

REQUEST_LENGTH_KEY = 'call_args_bytes'
""" Lenght of request data

Set by ``TruncateRequestFilter`` to the original length of data in
``REQUEST_KEY``.

"""

RESPONSE_LENGTH_KEY = 'return_bytes'
""" Lenght of response data

Set by ``TruncateResponseFilter`` to the original length of data in
``RESPONSE_KEY``.

"""

RESPONSE_STATUS_KEY = 'status'


RESPONSE_TIME_KEY = 'response_time'


EXCEPTION_KEY = 'error'


ENTRYPOINT_NAME_KEY = 'provider_name'
""" Name of the entrypoint service method

A key holding the entrypoint service method name e.g. ``'get_user'``.

"""

ENTRYPOINT_TYPE_KEY = ''
""" Name of the entrypoint type

A key holding the entrypoint type name e.g. ``'Rpc'``.

"""

ENTRYPOINT_PATH = ''
""" Entrypoint path

A key holding the name of the service and the name of the entrypoint method
e.g. ``'users.get_user'``.

"""


ADAPTER_OVERRIDES = {
    'nameko.web.handlers.HttpRequestHandler': (
        'nameko_entrypoint_logger.adapters.HttpRequestHandlerAdapter'),
}
"""
Default adapter overrides setup

Sets an override for Nameko built-in HttpRequestHandler. Extra overrides
coming from config are merged in.

"""


CONFIG_KEY = 'ENTRYPOINT_LOGGER'
ADAPTERS_CONFIG_KEY = 'ADAPTERS'
