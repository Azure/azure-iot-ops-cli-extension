# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
Structured test logging helper for integration tests.

Emits colored output via ``print()`` when ``PRETTY_LOG=1`` is set in the
environment; otherwise falls back to plain ``logger.warning()`` for standard
pytest log capture.

Usage::

    with TestLog("test_my_function", total_steps=5) as log:
        with log.step(1, "Create Device"):
            result = log.run_command("az iot ops ns device create ...")
            log.detail(f"id={result['id']}")

        with log.step(2, "Verify"):
            log.check("count == 2", count == 2)
"""

import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, List, Optional

from azure.cli.core.azclierror import CLIInternalError

from .helpers import run as _helpers_run
from knack.log import get_logger

logger = get_logger(__name__)


def _is_pretty() -> bool:
    """Check at call time, so monkeypatch / late env changes work."""
    return bool(os.environ.get("PRETTY_LOG"))


def _default_cmd_timeout() -> int:
    """Default timeout per CLI command (seconds). Override via TESTLOG_CMD_TIMEOUT env var."""
    return int(os.environ.get("TESTLOG_CMD_TIMEOUT", 300))


_ANSI_RESET = "\033[0m"
_ANSI = {
    "gold": "\033[38;2;202;157;100m",   # #CA9D64 – sandy gold
    "sage": "\033[38;2;153;166;103m",   # #99A667 – sage olive
    "terra": "\033[38;2;181;92;56m",     # #B55C38 – terracotta
    "clay": "\033[38;2;170;163;155m",   # #AAA39B – warm gray
    "dim": "\033[38;2;84;74;70m",       # #544A46 – muted gray
}


def _ts() -> str:
    """Current UTC time as HH:MM:SS."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _fmt_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m{secs:.0f}s"


def _log(msg: str, color: str = ""):
    """Emit a single log line.  Uses ANSI color when ``PRETTY_LOG`` is set,
    otherwise falls back to ``logger.warning()`` for pytest log capture."""
    if _is_pretty():
        ansi = _ANSI.get(color, "")
        if ansi:
            print(f"{ansi}{msg}{_ANSI_RESET}", flush=True)
        else:
            print(msg, flush=True)
    else:
        if msg.strip():
            logger.warning(msg)


class TestLog:
    """Context manager that provides structured step-based test logging.

    Usage::

        with TestLog("test_my_function", total_steps=5) as log:
            with log.step(1, "Create Device"):
                result = log.run_command(
                    "az iot ops ns device create --name dev-abc ...",
                    tracked_resources=tracked_resources,
                )
                log.detail(f"id={result['id']}")

            with log.step(2, "Export datasets"):
                export = log.run_command("az iot ops ns asset opcua dataset export ...")
                log.check("count == 2", export["dataset_count"] == 2)
    """

    def __init__(self, test_name: str, total_steps: int):
        self.test_name = test_name
        self.total_steps = total_steps
        self._test_start = 0.0

    def __enter__(self):
        self._test_start = time.monotonic()
        _log("")
        _log(f"▶ TEST: {self.test_name}", "gold")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = _fmt_duration(time.monotonic() - self._test_start)
        if exc_type is not None:
            _log(f"✗ FAIL ({elapsed}) – {exc_type.__name__}: {exc_val}", "terra")
        else:
            _log(f"✓ PASS ({elapsed})", "sage")
        return False

    class _Step:
        """Context manager for a single numbered step."""

        def __init__(self, log: "TestLog", num: int, description: str):
            self._log = log
            self._num = num
            self._description = description
            self._start = 0.0

        def __enter__(self):
            self._start = time.monotonic()
            _log("")
            _log(
                f"Setup {self._num}/{self._log.total_steps} ) "
                f"{self._description} · {_ts()}",
                "gold",
            )
            return self._log

        def __exit__(self, exc_type, exc_val, exc_tb):
            elapsed = _fmt_duration(time.monotonic() - self._start)
            if exc_type is not None:
                _log(f"  ⚠ FAILED: {exc_val}", "terra")
            _log(f"  ⏱ ({elapsed})", "dim")
            return False

    def step(self, num: int, description: str) -> "_Step":
        """Create a numbered step context."""
        return self._Step(self, num, description)

    def run_command(
        self,
        command: str,
        tracked_resources: Optional[List[str]] = None,
        expect_failure: bool = False,
        timeout: Optional[int] = None,
    ) -> Any:
        """Run a CLI command with logging. Optionally track resource IDs for cleanup."""
        _log(f"  › {command}", "sage")

        cmd_timeout = timeout if timeout is not None else _default_cmd_timeout()
        try:
            parsed = _helpers_run(
                command, expect_failure=expect_failure, timeout=cmd_timeout
            )
        except subprocess.TimeoutExpired:
            _log(f"  ⚠ command timed out after {cmd_timeout}s", "terra")
            raise CLIInternalError(f"Command timed out after {cmd_timeout}s: {command}")
        except CLIInternalError as e:
            err_lines = str(e).strip().splitlines()[:3]
            for line in err_lines:
                _log(f"  ↳ {line}", "clay")
            raise

        if tracked_resources is not None and isinstance(parsed, dict) and "id" in parsed:
            tracked_resources.append(parsed["id"])
            _log(f"  ↳ id={parsed['id']}", "clay")

        return parsed

    def detail(self, message: str):
        """Print an indented detail line."""
        _log(f"  ↳ {message}", "clay")

    def check(self, description: str, condition: bool, actual: Any = None):
        """Assert with logging."""
        if condition:
            _log(f"  ✓ {description}", "sage")
        else:
            msg = f"  ⚠ {description}"
            if actual is not None:
                msg += f" (actual: {actual})"
            _log(msg, "terra")
            assert condition, f"Check failed: {description} (actual: {actual})"
