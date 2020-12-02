.. image:: https://travis-ci.org/nameko/nameko-tracer.svg?branch=master
    :target: https://travis-ci.org/nameko/nameko-tracer

========================
Nameko Entrypoint Tracer
========================

Usage
=====

Install from PyPI:

.. code:: console

    pip install nameko-tracer


Add ``nameko_tracer.Tracer`` dependency provider to your service
plus add a simple RPC entrypoint so we have an endpoint to trace:


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


Now, if you start your service in a shell:

.. code:: console

    $ nameko run traced

And invoke the `test` entrypoint in another:

.. code:: console

    $ nameko shell
    In [1]: n.rpc.traced.hello(name='ナメコ')
    Out[2]: 'Hello, ナメコ!'

You should see two log records printed out in the first shell:

.. code:: console

    $ nameko run traced
    starting services: traced
    Connected to amqp://guest:***@127.0.0.1:5672//
    [traced.hello.8eb11de2-0b28-495d-af91-98bd6a051bca] entrypoint call trace
    [traced.hello.8eb11de2-0b28-495d-af91-98bd6a051bca] entrypoint result trace

The output does not tell much, given the default logging formatter prints
just the message. But there's much more on the log records, to get it out
let's configure service logging and customize the formatter to include the
trace details (the tracer adds safely serialisable details to ``nameko_trace``
attribute of the log record):

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

Stop the service and start it again pointing to the new config file:

.. code:: console

    $ nameko run traced --config config.yaml

And invoke the ``test`` entrypoint again in the second shell:

.. code:: console

    $ nameko shell
    In [1]: n.rpc.traced.hello(name='ナメコ')
    Out[1]: 'Hello, ナメコ!'
    In [2]: n.rpc.traced.hello(name='ナメコ')
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
formatter of the trace log record attribute. Now reconfigure the logging to
use ``nameko_tracer.formatters.JSONFormatter``:

.. code:: yaml

    # config.yaml

    AMQP_URI: 'pyamqp://guest:guest@localhost'
    LOGGING:
        version: 1
        formatters:
            tracer:
                (): nameko_tracer.formatters.JSONFormatter
        handlers:
            tracer:
                class: logging.StreamHandler
                formatter: tracer
        loggers:
            nameko_tracer:
                level: INFO
                handlers: [tracer]

After restarting the service with the updated config and after invoking the
testing call you will find the traces logged as JSON:

.. code:: console

    $ nameko run traced --config config.yaml
    {"call_id": "traced.hello.19522441-9581-484b-bad5-8d14b8b5c291", "call_args_red
    acted": false, "service": "traced", "entrypoint": "traced.hello", "provider": "
    Rpc", "lifecycle_stage": "request", "context_data": {}, "call_stack": ["standal
    ...

Find more about what's included in the trace in the Trace Data section.


Trace data
==========

TODO more words here ...

The **request** stage trace includes the following details:

- A **timestamp**.
- Entrypoint **metadata** consisting of:

  - service name
  - entrypoint method name
  - entrypoint type (e.g. ``Rpc``),
  - worker context data

- Tracking data with **call ID** and **call ID stack** holding a chain of
  call IDs of all consecutive calls leading to this one.
- Entrypoint **call arguments**. The tracer honours ``sensitive_variables``
  of each entrypoint and redacts values of sensitive arguments before
  placing them on the trace (there is also a flag saying whether the call
  arguments were redacted).

The **response** stage trace includes same details as the *request* stage
trace plus the following additional response specific fields:

- Response **status** which is either ``success`` or ``error`` in case the
  entrypoint execution failed.
- **Result** returned by the entrypoint (the package includes a logging
  filter for truncating the response if needed).
- **Exception** details if the entrypoint execution failed.
- **Response time** saying how long it took to process the entrypoint.

Each trace also includes a stage key saying what stage the trace is for.

See ``constants`` module for the exact key names.


JSON Trace Formatter
====================

The package includes ``nameko_tracer.formatters.JSONFormatter`` - a simple,
but handy formatter which takes ``nameko_trace`` attribute of the log record
and formats it as JSON string.


Truncation Filters
==================

The package also includes two filters for truncating bulky parts of trace data.
This is useful for reducing the amount of data ending up in your logs.

* ``nameko_tracer.filters.TruncateCallArgsFilter``
* ``nameko_tracer.filters.TruncateResponseFilter``

The truncating filter (``TruncateCallArgsFilter``) takes the following
arguments:

* ``entrypoints`` - a list of regex strings identifying entrypoints whose
  call arguments data should be truncated when logging. Defaults to an empty
  list - you have to provide an input in order to make this filter to take
  any effect.
* ``max_len`` - an integer representing the number of characters to keep.
  Defaults to ``100``.

The response truncating filter (``TruncateResponseFilter``) takes the following
arguments:

* ``entrypoints`` - a list of regex strings identifying entrypoints whose
  response data should be truncated when logging. Defaults to
  ``"^get_|^list_|^query_"``.
* ``max_len`` - an integer representing the number of characters to keep.
  Defaults to ``100``.

Both filters add an additional flag to the trace saying whether the trimming
was applied.

Note that the filters first serialise the input to a string before applying
the truncation. If the length of string representation of the input is within
the ``max_len`` limit, the input is kept untouched.

An example of configuring logging to use the truncation filters:

.. code:: yaml

    # config.yaml

    AMQP_URI: 'pyamqp://guest:guest@localhost'
    LOGGING:
        version: 1
        filters:
            truncate_request_trace:
                (): nameko_tracer.filters.TruncateCallArgsFilter
                entrypoints:
                    - insert_big_data
                max_len: 200
            truncate_response_trace:
                (): nameko_tracer.filters.TruncateResponseFilter
        formatters:
            tracer:
                (): nameko_tracer.formatters.JSONFormatter
        handlers:
            tracer:
                class: logging.StreamHandler
                formatter: tracer
        loggers:
            nameko_tracer:
                level: INFO
                handlers: [tracer]
                filters:
                    - truncate_request_trace
                    - truncate_response_trace


Custom Adapters
===============

TODO describe ...
