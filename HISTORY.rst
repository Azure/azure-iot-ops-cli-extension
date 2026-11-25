.. :changelog:

===============
Release History
===============

unreleased
==========

* Prepare CLI ``2.12.0a2`` with AIO 2612 GA-channel, preview-channel, and Fairfax qualification inputs.
  Public GA and preview retain the upstream integration train. Fairfax uses the shared 2612 instance template
  with AIO ``1.5.77 stable`` while retaining ``1.5.46 stable`` as a supported upgrade source.
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
