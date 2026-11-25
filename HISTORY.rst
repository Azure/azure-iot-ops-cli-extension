.. :changelog:

===============
Release History
===============

unreleased
==========

* ``iot ops identity assign --usage schema``: Federate the ``aio-edge-registry`` service account on preview runtimes,
  which run the schema registry as ``aio-edge-registry``. GA runtimes still use ``adr-schema-registry``.
  ``iot ops clone`` also replicates existing ``aio-edge-registry`` federated credentials.

* Prepare CLI ``2.12.0a1`` with AIO 2612 GA-channel and preview-channel qualification inputs.
  Both bundled Public runtimes retain the upstream integration train. The existing Fairfax 2610 inputs are unchanged.
  The Fairfax profile reports release 2612 to align with Public; its source and runtime versions remain unchanged.
* Preview deployments use the public connector registry and updated MCP policy actions.
  The source Edge Registry resource remains disabled by default, and the MCP Reader policy includes ``broker_metadata``.
  Both Public runtime channels support ``--sku Standard`` and ``--sku Essentials``; leaving SKU unset preserves defaults.
* ``iot ops support create-bundle``: Collect observability resources labelled ``meso-gateway``
  and ``meso-node``, while retaining support for the older observability labels.
* Initial baseline.
* ``iot ops check``: Stop requiring the retired MQTT broker diagnostics Service and pods.
  Broker diagnostics configuration, diagnostics probe, and other runtime health checks are unchanged.
* ``iot ops support create-bundle``: Warn when requested internal broker traces are unavailable
  because the diagnostics pod is absent, as expected in AIO 2610 GA/preview and later.
  Other resources and pod logs are still collected. Legacy trace collection remains supported,
  and trace collection failures are now visible as warnings.
