Release Notes
=============


Version 1.3.0
-------------

Release 2020-12-02

* Add PrettyJSONFormatter useful for development of Nameko services


Version 1.2.0
-------------

Released 2018-07-24

* Add origin call ID to log message


Version 1.1.0
-------------

Released 2018-06-04

* Truncation filters are not restricted by lifecycle-stage


Version 1.0.8
-------------

Released 2017-11-28

* Better NoneType serialisation


Version 1.0.7
-------------

Released 2017-10-27

* Fix for handling of non werkzeug responses of HTTP entrypoints
* Sensitive arguments compatibility with Nameko


Version 1.0.6
-------------

Released 2017-09-28

* Fix response truncating filter - deal with failing entrypoint responses


Version 1.0.5
-------------

Released 2017-09-06

* Add call ID to log message


Version 1.0.4
-------------

Released 2017-08-31

* Flatten exception details to separate trace keys
* Fix hostname trace key population


Version 1.0.2
-------------

Released 2017-08-24

* Add Elasticsearch friendly JSON formatter (extra JSON serialisation
  of free structured fields)


Version 1.0.1
-------------

Released 2017-08-17

* Open-sourced
* Tracer extension based on logging adapters and using Python logging
  built-in building blocks
