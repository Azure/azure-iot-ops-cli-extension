# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
sitecustomize hook to enable coverage.py measurement inside subprocesses.

Integration tests invoke the CLI as child ``az iot ops ...`` processes (see
``azext_edge/tests/helpers.py::run`` -> ``subprocess.run``). coverage.py only
traces the process it starts in, so those child processes would otherwise be
invisible to coverage, which is why integration coverage reads as ~0%.

When this directory is on ``PYTHONPATH`` and ``COVERAGE_PROCESS_START`` points at
the coverage config, Python imports this module at interpreter startup and
``coverage.process_startup()`` arms measurement for the child process. It is a
no-op when ``COVERAGE_PROCESS_START`` is unset and when coverage is unavailable,
so it is safe for every process that inherits ``PYTHONPATH``.
"""

try:
    import coverage

    coverage.process_startup()
except Exception:  # pragma: no cover - never break a subprocess if coverage is missing
    pass
