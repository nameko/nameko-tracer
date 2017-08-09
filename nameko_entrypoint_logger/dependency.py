import logging
import socket
from datetime import datetime
from weakref import WeakKeyDictionary

from nameko.extensions import DependencyProvider

from nameko_entrypoint_logger import adapters, constants, utils


logger = logging.getLogger(__name__)


class EntrypointLogger(DependencyProvider):
    """ Entrypoint logging dependency

    Logs call and result details about entrypoints fired.

    """

    def __init__(self):
        self.logger = None
        self.adapters = {}
        self.custom_adapters = {}
        self.worker_timestamps = WeakKeyDictionary()

    def setup(self):
        config = self.container.config.get(constants.CONFIG_KEY, {})

        self.configure_adapters(constants.DEFAULT_ADAPTERS)
        self.configure_adapters(config.get(constants.ADAPTERS_CONFIG_KEY, {}))

        self.logger = logging.getLogger(constants.LOGGER_NAME)

    def configure_adapters(self, adapters_config):
        for entrypoint_path, adapter_path in adapters_config.items():
            entrypoint_class = utils.import_by_path(entrypoint_path)
            adapter_class = utils.import_by_path(adapter_path)
            self.custom_adapters[entrypoint_class] = adapter_class

    def adapter_factory(self, entrypoint_class):
        if entrypoint_class in self.custom_adapters:
            adapter_class = self.custom_adapters[entrypoint_class]
        else:
            adapter_class = adapters.DefaultAdapter
        extra = {constants.HOSTNAME_KEY: socket.gethostname()}
        return adapter_class(self.logger, extra=extra)

    def get_adapter(self, worker_ctx):
        key = type(worker_ctx.entrypoint)
        try:
            return self.adapters[key]
        except KeyError:
            self.adapters[key] = self.adapter_factory(key)
            return self.adapters[key]

    def worker_setup(self, worker_ctx):
        """ Log entrypoint call details
        """

        timestamp = datetime.utcnow()
        self.worker_timestamps[worker_ctx] = timestamp

        try:
            extra = {
                'stage': constants.Stage.request,
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
                'stage': constants.Stage.response,
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
