from collections import defaultdict
from datetime import datetime
import logging
import socket
from weakref import WeakKeyDictionary

from nameko.extensions import DependencyProvider

from nameko_tracer import adapters, constants, utils


logger = logging.getLogger(__name__)


class Tracer(DependencyProvider):
    """ Entrypoint logging dependency

    Logs call and result details about entrypoints fired.

    """

    def __init__(self):
        self.logger = None
        self.adapter_types = defaultdict(lambda: adapters.DefaultAdapter)
        self.worker_timestamps = WeakKeyDictionary()

    def setup(self):
        config = self.container.config.get(constants.CONFIG_KEY, {})

        self.configure_adapter_types(constants.DEFAULT_ADAPTERS)
        self.configure_adapter_types(
            config.get(constants.ADAPTERS_CONFIG_KEY, {}))

        self.logger = logging.getLogger(constants.LOGGER_NAME)

    def configure_adapter_types(self, adapters_config):
        for entrypoint_path, adapter_path in adapters_config.items():
            entrypoint_class = utils.import_by_path(entrypoint_path)
            adapter_class = utils.import_by_path(adapter_path)
            self.adapter_types[entrypoint_class] = adapter_class

    def adapter_factory(self, worker_ctx):
        adapter_class = self.adapter_types[type(worker_ctx.entrypoint)]
        extra = {'hostname': socket.gethostname()}
        return adapter_class(self.logger, extra=extra)

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
            adapter = self.adapter_factory(worker_ctx)
            adapter.info(
                '[%s] entrypoint call trace',
                worker_ctx.call_id,
                extra=extra)
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
            adapter = self.adapter_factory(worker_ctx)
            if exc_info:
                adapter.warning(
                    '[%s] entrypoint result trace',
                    worker_ctx.call_id,
                    extra=extra)
            else:
                adapter.info(
                    '[%s] entrypoint result trace',
                    worker_ctx.call_id,
                    extra=extra)
        except Exception:
            logger.warning('Failed to log entrypoint trace', exc_info=True)
