from enum import Enum


class Stage(Enum):
    """ Entrypoint stage
    """
    request = 'request'
    response = 'response'


class Status(Enum):
    """ Entrypoint result status
    """
    success = 'success'
    error = 'error'


LOGGER_NAME = 'nameko_tracer'
""" Name of the logger used for entrypoint logging

Use this name to configure entrypoint logging in ``LOGGING`` setting
of Nameko config.

"""

TRACE_KEY = 'nameko_trace'
""" Name of the log record attribute holding the serialisable details

Contains gathered entrypoint call and result details in serialisable
and compact form.

"""


TIMESTAMP_KEY = 'timestamp'
""" A key holding the entrypoint stage timestamp
"""


STAGE_KEY = 'stage'
""" A key holding the lifecycle stage (a value of one of ``Stage`` options)
"""


HOSTNAME_KEY = 'hostname'
""" A key holding the service host name
"""


REQUEST_KEY = 'call_args'
""" A key holding a dictionary of arguments passed to the entrypoint call
"""

REQUEST_REDACTED_KEY = 'call_args_redacted'
"""
A key holding a boolean value saying whether sensitive values of the
entrypoint call arguments were redacted.

"""

RESPONSE_KEY = 'response'
""" A key holding serialisable return value of the entrypoint.
"""

REQUEST_TRUNCATED_KEY = 'call_args_truncated'
"""
A key holding a boolean value saying whether the call args data were
truncated. Set by ``TruncateRequestFilter``.

"""

RESPONSE_TRUNCATED_KEY = 'response_truncated'
"""
A key holding a boolean value saying whether the result data were truncated.
Set by ``TruncateResponseFilter``.

"""

REQUEST_LENGTH_KEY = 'call_args_length'
""" A key holding the original call args data length

Set by ``TruncateRequestFilter`` to the original length of data in
``REQUEST_KEY``.

"""

RESPONSE_LENGTH_KEY = 'response_length'
""" A key holding the original result data length

Set by ``TruncateResponseFilter`` to the original length of data in
``RESPONSE_KEY``.

"""

RESPONSE_STATUS_KEY = 'status'
""" A key holding the result status (a value of one of ``Status`` options)
"""


RESPONSE_TIME_KEY = 'response_time'
""" A key holding the amount of time taken between the two stages
"""


ERROR_KEY = 'error'
""" A key holding exception details if the entrypoint resulted into an error
"""

SERVICE_NAME_KEY = 'service'
""" A key holding the name of the service
"""

ENTRYPOINT_NAME_KEY = 'entrypoint'
""" A key holding the entrypoint service method name e.g. ``'get_user'``
"""

ENTRYPOINT_TYPE_KEY = 'entrypoint_type'
""" A key holding the entrypoint type name e.g. ``'Rpc'``.
"""

ENTRYPOINT_PATH_KEY = 'entrypoint_path'
"""
A key holding the name of the service and the name of the entrypoint method
e.g. ``'users.get_user'``.

"""

CALL_ID_KEY = 'call_id'
""" A key holding the unique ID of the entrypoint call
"""

CALL_ID_STACK_KEY = 'call_id_stack'
""" A key holding the call ID stack ...
"""

CONTEXT_DATA_KEY = 'context_data'
""" A key holding the worker context data dictionary
"""

DEFAULT_ADAPTERS = {
    'nameko.web.handlers.HttpRequestHandler': (
        'nameko_tracer.adapters.HttpRequestHandlerAdapter'),
}
"""
Default adapter overrides setup

Sets an override for Nameko built-in HttpRequestHandler. Extra overrides
coming from config are merged in.

"""

CONFIG_KEY = 'TRACER'
ADAPTERS_CONFIG_KEY = 'ADAPTERS'
