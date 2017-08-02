from enum import Enum


class Stage(Enum):
    request = 'request'
    response = 'response'


RECORD_ATTR = 'data'
STAGE_KEY = 'lifecycle_stage'

REQUEST_KEY = 'call_args'
RESPONSE_KEY = 'return_args'

REQUEST_TRUNCATED_KEY = 'call_args_truncated'
RESPONSE_TRUNCATED_KEY = 'return_args_truncated'

REQUEST_LENGTH_KEY = 'call_args_bytes'
RESPONSE_LENGTH_KEY = 'return_bytes'

ENTRYPOINT_NAME_KEY = 'provider_name'

