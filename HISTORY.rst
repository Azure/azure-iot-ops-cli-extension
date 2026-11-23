.. :changelog:

===============
Release History
===============

unreleased
==========

* Initial baseline.
* ``iot ops upgrade``: Warn when ``connectors.image.tag`` pins the OPC UA connector image.
  Add ``--clear-connector-tag`` (``--cct``) to remove the pin while preserving unrelated settings.
* ``iot ops check``: Stop requiring the retired MQTT broker diagnostics Service and pods.
  Broker diagnostics configuration, diagnostics probe, and other runtime health checks are unchanged.
* ``iot ops support create-bundle``: Warn when requested internal broker traces are unavailable
  because the diagnostics pod is absent, as expected in AIO 2610 GA/preview and later.
  Other resources and pod logs are still collected. Legacy trace collection remains supported,
  and trace collection failures are now visible as warnings.
