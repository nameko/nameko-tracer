nameko-entrypoint-logger
========================

[Nameko](https://github.com/onefinestay/nameko) extension for logging entrypoint invocation to RabbitMQ   

Usage
-----

Assuming service is configured to run with RabbitMQ.  

Add Entrypoint logging configuration to your nameko config file:

```yaml

    # config.yaml
    ENTRYPOINT_LOGGING:
        EXCHANGE_NAME: "monitoring"
        ROUTING_KEY: "entrypoint_log"
        SERIALIZER: "json" # Optional. For example, json, raw, or pickle. Defaults to 'json'
        CONTENT_TYPE: "application/json" # Optional. Can be set to any valid MIME type. Defaults to 'application/json'
    ...
```

Include the `EntrypointLogger` dependency in your service class:

```python

    # service.py
    from nameko.web.handlers import http

    class Service(object):
        name = "demo_service"

        entrypoint_logger = EntrypointLogger()

        @http('GET', '/get/<int:value>')
        def get_method(self, request, value):
            return json.dumps({'success': true})
```

Run your service, providing the config file:

`$ nameko run service --config config.yaml`


Each time `get_method` entrypoint is executed one `request` and one `response` messages will be published to `monitoring` exchange with `entrypoint_log` routing key.

`$ curl --header "X-MyHeader: 123" --user-agent "My User Agent String" http://localhost:8000/get/999`

Sample Message: Lifecycle Stage: **request**

```json

{
    "lifecycle_stage": "request",
    "provider": "HttpRequestHandler",
    "service": "demo_service",
    "provider_name": "get_method",
    "entrypoint": "demo_service.get_method",
    "hostname": "BOB-MAC.lan",
    "timestamp": "2015-11-26T10:15:02.022680",
    "call_stack": [
        "demo_service.get_method.e390af6a-a425-487c-adfa-7e8c00b78fa4"
    ],
    "call_id": "demo_service.get_method.e390af6a-a425-487c-adfa-7e8c00b78fa4",    
    "call_args": {
        "args": "{\"value\": \"999\"}",
        "request": {
            "env": {
                "remote_addr": "127.0.0.1",
                "server_port": "8000",
                "server_name": "127.0.0.1"
            },
            "data": "{}",
            "url": "http://localhost:8000/get/999",
            "method": "GET",
            "headers": {
                "content_type": "text/plain",
                "accept": "*/*",
                "x_myheader": "123",
                "host": "localhost:8000",
                "user_agent": "My User Agent String"
            }
        }
    }   
}
```

Sample Message: Lifecycle Stage: **response**

```json

{
    "lifecycle_stage": "response",
    "provider": "HttpRequestHandler",
    "service": "demo_service",
    "provider_name": "get_method",
    "entrypoint": "demo_service.get_method",    
    "hostname": "BOB-MAC.lan",
    "timestamp": "2015-11-26T10:15:02.026442",
    "status": "success",
    "response_time": 0.003762,
    "call_stack": [
        "demo_service.get_method.e390af6a-a425-487c-adfa-7e8c00b78fa4"
    ],
    "call_id": "demo_service.get_method.e390af6a-a425-487c-adfa-7e8c00b78fa4",
    "call_args": {
        "args": "{\"value\": \"999\"}",
        "request": {
            "env": {
                "remote_addr": "127.0.0.1",
                "server_port": "8000",
                "server_name": "127.0.0.1"
            },
            "data": "{}",
            "url": "http://localhost:8000/get/999",
            "method": "GET",
            "headers": {
                "content_type": "text/plain",
                "accept": "*/*",
                "x_myheader": "123",
                "host": "localhost:8000",
                "user_agent": "My User Agent String"
            }
        }
    },
    "return_args": {
        "result_bytes": 14,
        "content_type": "application/json",
        "result": "{\"value\": 999}",
        "status_code": 200
    }
}
```
