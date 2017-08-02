from importlib import import_module
import logging
import socket
from datetime import datetime
from weakref import WeakKeyDictionary

from nameko.extensions import DependencyProvider

from nameko_entrypoint_logger.formatters import JSONFormatter
from nameko_entrypoint_logger import adapters, constants


logger = logging.getLogger(__name__)


class EntrypointLogger(DependencyProvider):
    """ Entrypoint logging dependency

    Logs call and result details about entrypoints fired.

    """

    def __init__(self):

        self.logger = None

        self.adapters = {}

        self.adapter_overrides = {}

        self.worker_timestamps = WeakKeyDictionary()

    def setup(self):

        self.logger = logging.getLogger(constants.LOGGER_NAME)

        adapter_overrides_config = constants.ADAPTER_OVERRIDES
        for entrypoint_path, adapter_path in adapter_overrides_config.items():
            entrypoint_class = import_string(entrypoint_path)
            adapter_class = import_string(adapter_path)
            self.adapter_overrides[entrypoint_class] = adapter_class

        config = self.container.config.get(constants.CONFIG_KEY, {})
        adapter_overrides_config = config.get(
            constants.ADAPTERS_CONFIG_KEY, {})
        for entrypoint_path, adapter_path in adapter_overrides_config.items():
            entrypoint_class = import_string(entrypoint_path)
            adapter_class = import_string(adapter_path)
            self.adapter_overrides[entrypoint_class] = adapter_class

    def adapter_factory(self, entrypoint_class, extra):
        if entrypoint_class in self.adapter_overrides:
            adapter_class = self.adapter_overrides[entrypoint_class]
        else:
            adapter_class = adapters.EntrypointAdapter
        return adapter_class(self.logger, extra=extra)

    def get_adapter(self, worker_ctx):
        key = type(worker_ctx.entrypoint)
        try:
            return self.adapters[key]
        except KeyError:
            extra = {constants.HOSTNAME_KEY: socket.gethostname()}
            self.adapters[key] = self.adapter_factory(key, extra)
            return self.adapters[key]

    def worker_setup(self, worker_ctx):
        """ Log entrypoint call details
        """

        timestamp = datetime.utcnow()
        self.worker_timestamps[worker_ctx] = timestamp

        try:
            extra = {
                'lifecycle_stage': constants.Stage.request,
                'worker_ctx': worker_ctx,
                'timestamp': timestamp,
            }
            adapter = self.get_adapter(worker_ctx)
            adapter.info('entrypoint call trace', extra=extra)
        except Exception:
            logger.warning('Failed to log entrypoint trace', exc_info=True)

    def worker_result(self, worker_ctx, result=None, exc_info=None):
        """ Log entrypoint result details
        """

        timestamp = datetime.utcnow()
        worker_setup_timestamp = self.worker_timestamps[worker_ctx]
        response_time = (timestamp - worker_setup_timestamp).total_seconds()

        try:
            extra = {
                'lifecycle_stage': constants.Stage.response,
                'worker_ctx': worker_ctx,
                'result': result,
                'exc_info_': exc_info,
                'timestamp': timestamp,
                'response_time': response_time,
            }
            adapter = self.get_adapter(worker_ctx)
            if exc_info:
                adapter.warning('entrypoint result trace', extra=extra)
            else:
                adapter.info('entrypoint result trace', extra=extra)
        except Exception:
            logger.warning('Failed to log entrypoint trace', exc_info=True)



def import_string(dotted_path):
    """
    Import a dotted module path and return the attribute/class designated by
    the last name in the path. Raise ImportError if the import failed.

    Borrowed from Django codebase -
    ``django.utils.module_loading.import_string``

    """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError as err:
        raise ImportError("%s doesn't look like a module path" % dotted_path) from err

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as err:
        raise ImportError('Module "%s" does not define a "%s" attribute/class' % (
            module_path, class_name)
        ) from err
