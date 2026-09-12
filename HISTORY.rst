.. :changelog:

===============
Release History
===============

unreleased
==========

* Initial baseline.
* `az iot ops upgrade` now retries transient token-acquisition and network
  failures (e.g. ``Connection reset by peer`` while acquiring an ARM token)
  instead of aborting; genuine errors still fail fast.
