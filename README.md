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


Each time `get_method` entrypoint is executed one `request` and one `response` messages will be published to `monitoring` exchange with `entry_point_log` routing key.

Sample Message: Lifecycle Stage: **request**

.. code-block:: json

{
    "lifecycle_stage": "request",
    "provider": "HttpRequestHandler",
    "service": "service_a",
    "provider_name": "post_method",
    "entrypoint": "service_a.post_method",
    "call_stack": [
        "service_a.post_method.e5288a58-b738-4a0a-8bfc-a6f8aec7564f"
    ],    
    "call_args": {
        "url": "http://localhost:8000/post",
        "method": "POST",
        "env": {
            "SERVER_PORT": "8000",
            "SERVER_NAME": "127.0.0.1",
            "REMOTE_ADDR": "127.0.0.1"
        },
        "headers": {
            "Host": "localhost:8000",
            "Content-Length": "109",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "User-Agent": "python-requests/2.8.1"
        },
        "data": "{\"message\": \"test_json_request\", \"service_b_timestamp\": \"2015-11-16T18:19:01.845601\", \"type\": \"request type\"}"
    },
    "call_id": "service_a.post_method.e5288a58-b738-4a0a-8bfc-a6f8aec7564f",
    "timestamp": "2015-11-16T18:19:01.861839",
    "hostname": "JAKUBS-MAC.ldn.gb.oslcorp.lan"
}

Sample Message: Lifecycle Stage: **response**

.. code-block:: json

{
    "lifecycle_stage": "response",
    "provider": "HttpRequestHandler",
    "service": "service_a",
    "provider_name": "post_method",
    "entrypoint": "service_a.post_method",
    "call_stack": [
        "service_a.post_method.e5288a58-b738-4a0a-8bfc-a6f8aec7564f"
    ],
    "call_args": {
        "url": "http://localhost:8000/post",
        "method": "POST",
        "env": {
            "SERVER_PORT": "8000",
            "SERVER_NAME": "127.0.0.1",
            "REMOTE_ADDR": "127.0.0.1"
        },
        "headers": {
            "Host": "localhost:8000",
            "Content-Length": "109",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
            "Connection": "keep-alive",
            "User-Agent": "python-requests/2.8.1"
        },
        "data": "{\"message\": \"test_json_request\", \"service_b_timestamp\": \"2015-11-16T18:19:01.845601\", \"type\": \"request type\"}"
    },
    "status": "success",
    "response_time": 0.002317,
    "http_response": {
        "content_type": "application/json",
        "content_length": 17,
        "status_code": 200,
        "data": "{\"success\": true}"
    },
    "call_id": "service_a.post_method.e5288a58-b738-4a0a-8bfc-a6f8aec7564f",
    "timestamp": "2015-11-16T18:19:01.864156",
    "hostname": "JAKUBS-MAC.ldn.gb.oslcorp.lan"
}
