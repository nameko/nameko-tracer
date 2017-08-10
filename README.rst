=================
Entrypoint Tracer
=================

A `Nameko`_ extension for logging details about entrypoints fired.


Usage
=====

Install from PyPI:

.. code:: console

    pip install entrypoint-tracer


Add ``Tracer`` dependency provider to your service:


.. code:: python

    # traced.py

    from nameko.rpc import rpc
    from nameko_tracer import Tracer


    class Service:

        name = 'traced'

        tracer = Tracer()

        @rpc
        def hello(self, name):
            return 'Hello, {}!'.format(name)


Now, if you start your service in a shell

.. code:: console

    $ nameko run traced

And invoke the `test` entrypoint in another:

.. code:: console

    $ nameko shell
    In [1]: n.rpc.traced.hello(name='ナメコ')
    Out[2]: 'Hello, ナメコ!'

You should see two log records printed in the first shell:

.. code:: console

    $ nameko run traced
    starting services: traced
    Connected to amqp://guest:***@127.0.0.1:5672//
    entrypoint call trace
    entrypoint result trace

That does not tell much, given the default logging formatter prints just the
message. There's much more on the log records, let's configure service logging
and customize the formatter:

.. code:: yaml

    # config.yaml

    AMQP_URI: 'pyamqp://guest:guest@localhost'
    LOGGING:
        version: 1
        formatters:
            tracer:
                format: "[%(name)-12s] %(nameko_trace)s"
        handlers:
            tracer:
                class: logging.StreamHandler
                formatter: tracer
        loggers:
            nameko_tracer:
                level: INFO
                handlers: [tracer]

Stop the service and start it again with pointing to the config file:

.. code:: console

    $ nameko run traced --config config.yaml

And invoke the ``test`` entrypoint again in the second shell:

.. code:: console

    $ nameko shell
    In [1]: n.rpc.traced.hello(name='ナメコ')
    Out[2]: 'Hello, ナメコ!'

In the first shell where the service runs you'll find the string
representation of the gathered trace information printed out:

.. code:: console

    $ nameko run traced --config config.yaml
    [nameko_tracer] {'call_args_redacted': False, 'context_data': {}, 'entrypoint':
     'traced.hello', 'call_id': 'traced.hello.f51733a0-1851-47e6-9d47-29bef5eaf581'
    , 'provider': 'Rpc', 'timestamp': datetime.datetime(2017, 8, 10, 18, 7, 12, 106
    972), 'service': 'traced', 'call_stack': ['standalone_rpc_proxy.call.14caabf9-8
    92f-4ab2-b04b-e0fb90167fe5', 'traced.hello.f51733a0-1851-47e6-9d47-29bef5eaf581
    '], 'call_args': {'name': 'ナメコ'}, 'lifecycle_stage': 'request', 'provider_na
    me': 'hello'}
    [nameko_tracer] {'call_args_redacted': False, 'context_data': {}, 'call_id': 't
    raced.hello.f51733a0-1851-47e6-9d47-29bef5eaf581', 'provider': 'Rpc', 'return_a
    rgs': 'Hello, ナメコ!', 'response_time': 0.023348, 'call_stack': ['standalone_r
    pc_proxy.call.14caabf9-892f-4ab2-b04b-e0fb90167fe5', 'traced.hello.f51733a0-185
    1-47e6-9d47-29bef5eaf581'], 'entrypoint': 'traced.hello', 'timestamp': datetime
    .datetime(2017, 8, 10, 18, 7, 12, 130320), 'status': 'success', 'service': 'tra
    ced', 'call_args': {'name': 'ナメコ'}, 'lifecycle_stage': 'response', 'provider
    _name': 'hello'}

The traces include comprehensive information about the entrypoint fired and
it would be more practical to have the details serialised in a format which
is readable by both humans and machines. The tracer comes with a simple JSON
formatter of the trace log record attribute ``nameko_tracer.formatters.JSONFormatter``:

.. code:: yaml

    # config.yaml

    AMQP_URI: 'pyamqp://guest:guest@localhost'
    LOGGING:
        version: 1 
        formatters:
            tracer:
                class: nameko_tracer.formatters.JSONFormatter
        handlers:
            tracer:
                class: logging.StreamHandler
                formatter: tracer
        loggers:
            nameko_tracer:
                level: INFO
                handlers: [tracer]

Now after restarting the service with the updated config and invoking the
testing call you will find the traces logged as JSON:

.. code:: console

    $ nameko run traced --config config.yaml
    {"call_id": "traced.hello.19522441-9581-484b-bad5-8d14b8b5c291", "call_args_red
    acted": false, "service": "traced", "entrypoint": "traced.hello", "provider": "
    Rpc", "lifecycle_stage": "request", "context_data": {}, "call_stack": ["standal
    ...
