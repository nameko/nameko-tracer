nameko-entrypoint-logger
========================

[Nameko](https://github.com/onefinestay/nameko) extension for logging entrypoint invocation to RabbitMQ   

Usage
-----

Assuming service is configured to run with RabbitMQ.  

Add Entrypoint logging configuration to your nameko config file:

.. code-block:: yaml

    # config.yaml
    ENTRYPOINT_LOGGING:
		EXCHANGE_NAME: "monitoring"
		EVENT_TYPE: "entry_point_log"
	...

Include the `EntrypointLogger` dependency in your service class:

.. code-block:: python

    # service.py
    from nameko.web.handlers import http
    from nameko_sentry import SentryReporter

    class Service(object):
        name = "demo"

        entrypoint_logger = EntrypointLogger()

        @http('GET', '/get/<int:value>')
    	def get_method(self, request, value):
            return json.dumps({'success': true})

Run your service, providing the config file:

.. code-block:: shell

    $ nameko run service --config config.yaml


Each time `get_method` entrypoint is executed 2 messages will be published to `monitoring` exchange with `entry_point_log` routing key.

# TODO Message JSON examples.

