# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Reusable Rich-based workflow progress display for multi-step CLI operations."""

import threading
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

from rich.console import Console
from rich.live import Live
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text


_DISPLAY_WIDTH = 56
_DOT_CHAR = "."


def format_dot_leader(
    name: str, detail: str, width: int = _DISPLAY_WIDTH, indent: str = "    ", dot_char: str = _DOT_CHAR,
) -> str:
    """Format a line with dot-leaders connecting name to right-aligned detail.

    Produces lines like:  ``    Topic space ............... created``
    Shared between WorkflowDisplay step rendering and static summary tables.
    """
    content_width = width - len(indent)
    dots_needed = content_width - len(name) - len(detail) - 2  # 2 spaces flanking dots
    dots_needed = max(dots_needed, 2)
    dots = f" {dot_char * dots_needed} "
    return f"{indent}{name}{dots}{detail}"


def render_summary(
    title: str,
    sections: Dict[str, Union[List[Tuple[str, str]], List[str]]],
    footer: str = "",
) -> None:
    """Print a static Rich summary table to stderr.

    Each section is a category header with items listed below it.
    Items can be tuples ``(name, detail)`` rendered with dot-leaders, or plain
    strings rendered as simple indented lines.
    Empty sections are silently skipped.

    Args:
        title: Bold header line.
        sections: Ordered dict of {category_name: items}.  Items may be
            ``[(name, detail), ...]`` for dot-leader layout or ``[label, ...]``
            for plain hierarchical listing.
        footer: Optional dim-styled note line at the bottom.
    """
    grid = Table.grid(padding=(0, 0))
    grid.add_column()

    grid.add_row(Text(f" {title}", style="bold"))
    grid.add_row(Text(""))

    has_items = False
    for category, items in sections.items():
        if not items:
            continue
        has_items = True
        grid.add_row(Text(f"  {category}"))
        for item in items:
            if isinstance(item, tuple):
                grid.add_row(Text(format_dot_leader(item[0], item[1])))
            else:
                grid.add_row(Text(f"    {item}"))
        grid.add_row(Text(""))

    if not has_items:
        grid.add_row(Text("  No resources found.", style="dim"))
        grid.add_row(Text(""))

    if footer:
        grid.add_row(Text(f"  {footer}", style="dim"))
        grid.add_row(Text(""))

    Console(stderr=True).print(grid)


class StepState(Enum):
    """Workflow step lifecycle states."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETE = "complete"
    SKIPPED = "skipped"
    FAILED = "failed"


class WorkflowDisplay:
    """Thread-safe progress display for multi-step CLI workflows.

    Renders categorized steps with dot-leader alignment, caller-supplied status words,
    and color-coded category headers. All output goes to stderr via Console(stderr=True)
    to keep stdout clean for JSON return values.

    Supports transient mode (display vanishes on exit) for commands that return JSON,
    and persistent mode (display remains) for commands that return None. Full suppression
    via no_progress for CI/CD automation.

    Usage:
        categories = {"Analyzing": ["Step 1", "Step 2"], "Building": ["Step 3"]}
        with WorkflowDisplay("My Workflow", categories) as display:
            display.update_step("Analyzing", "Step 1", StepState.ACTIVE)
            # ... do work ...
            display.update_step("Analyzing", "Step 1", StepState.COMPLETE, "done")
    """

    def __init__(
        self,
        title: str,
        categories: Dict[str, List[str]],
        transient: bool = True,
        no_progress: bool = False,
        refresh_per_second: int = 8,
    ) -> None:
        self._title = title
        self._transient = transient
        self._no_progress = bool(no_progress)
        self._refresh_per_second = refresh_per_second

        self._console = Console(stderr=True)
        self._lock = threading.Lock()
        self._live: Optional[Live] = None
        self._progress_bar: Optional[Progress] = None
        self._task_id: Optional[int] = None

        # Ordered step state: {category: {step_name: [state, detail]}}
        # Dict insertion order preserved (Python 3.7+)
        self._steps: Dict[str, Dict[str, list]] = {}
        for cat, steps in categories.items():
            self._steps[cat] = {}
            for step in steps:
                self._steps[cat][step] = [StepState.PENDING, ""]

    def __enter__(self) -> "WorkflowDisplay":
        if self._no_progress:
            return self
        if not self._transient:
            self._progress_bar = Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=20),
                TextColumn("Elapsed:"),
                TimeElapsedColumn(),
                auto_refresh=False,
            )
            self._task_id = self._progress_bar.add_task(description="Working...", total=None)
        self._live = Live(
            console=self._console,
            transient=self._transient,
            refresh_per_second=self._refresh_per_second,
        )
        # Override get_renderable so Live's auto-refresh daemon thread calls _render()
        # on each cycle, giving us live elapsed time updates without manual live.update()
        # calls on every state change.
        self._live.get_renderable = self._render
        self._live.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        if self._progress_bar is not None and self._task_id is not None:
            self._progress_bar.update(self._task_id, description="Done.")
            self._progress_bar.stop_task(self._task_id)
        if self._live is not None:
            self._live.__exit__(*exc)
            self._live = None

    def update_step(self, category: str, step: str, state: StepState, detail: str = "") -> None:
        """Transition a step to a new state with an optional caller-supplied status word.

        The display is domain-agnostic — callers choose contextually appropriate status
        words like 'created', 'exists', 'removed', 'not found', 'failed: <reason>'.
        """
        if self._no_progress:
            return
        with self._lock:
            self._set_step(category, step, state, detail)

    def complete_category(self, category: str) -> None:
        """Mark all remaining PENDING steps in a category as COMPLETE with 'done'.

        Useful when all steps in a phase succeed and the caller wants to advance the
        entire category in one call rather than updating each step individually.
        """
        if self._no_progress:
            return
        with self._lock:
            if category not in self._steps:
                raise ValueError(f"Unknown category: {category!r}")
            for step_entry in self._steps[category].values():
                if step_entry[0] == StepState.PENDING:
                    step_entry[0] = StepState.COMPLETE
                    if not step_entry[1]:
                        step_entry[1] = "done"

    def _set_step(self, category: str, step: str, state: StepState, detail: str) -> None:
        """Update a step entry. Must be called under self._lock."""
        if category not in self._steps:
            raise ValueError(f"Unknown category: {category!r}")
        if step not in self._steps[category]:
            raise ValueError(f"Unknown step {step!r} in category {category!r}")
        self._steps[category][step] = [state, detail]

    def _render(self) -> Table:
        """Build the display grid from a snapshot of current state.

        Called by Rich Live's auto-refresh daemon thread on each refresh cycle —
        acquires lock briefly for the state snapshot, then builds the grid outside
        the lock to minimize contention with worker threads.
        """
        with self._lock:
            snapshot: Dict[str, Dict[str, Tuple[StepState, str]]] = {
                cat: {step: (entry[0], entry[1]) for step, entry in steps.items()}
                for cat, steps in self._steps.items()
            }

        grid = Table.grid(padding=(0, 0))
        grid.add_column()

        # Title
        grid.add_row(Text(f" {self._title}", style="bold"))
        grid.add_row(Text(""))

        for cat, steps in snapshot.items():
            cat_style = self._category_style(steps)
            grid.add_row(Text(f"  {cat}", style=cat_style))

            for step_name, (state, detail) in steps.items():
                grid.add_row(self._render_step(step_name, state, detail))

            grid.add_row(Text(""))

        # Animated progress footer for non-transient displays
        if self._progress_bar is not None:
            grid.add_row(self._progress_bar)
            grid.add_row(Text(""))

        return grid

    @staticmethod
    def _category_style(steps: Dict[str, Tuple[StepState, str]]) -> str:
        """Derive category header color from the aggregate state of its steps."""
        states = [s for s, _ in steps.values()]
        if any(s == StepState.FAILED for s in states):
            return "red"
        if any(s == StepState.ACTIVE for s in states):
            return "cyan"
        if all(s in (StepState.COMPLETE, StepState.SKIPPED) for s in states):
            return ""
        if all(s == StepState.PENDING for s in states):
            return "dim"
        # Mix of completed/skipped and pending — category is in progress
        return "cyan"

    def _render_step(self, name: str, state: StepState, detail: str) -> Text:
        """Render a single step with formatting appropriate to its state."""
        indent = "    "

        if state == StepState.PENDING:
            return Text(f"{indent}{name}", style="dim")

        if state == StepState.ACTIVE:
            return Text(f"{indent}{name} ...", style="cyan")

        # Terminal states: dot leaders connecting step name to right-aligned status word
        status_word = detail or state.value
        line = format_dot_leader(name, status_word)

        style_map = {
            StepState.COMPLETE: "",
            StepState.SKIPPED: "dark_khaki",
            StepState.FAILED: "red",
        }
        return Text(line, style=style_map.get(state, ""))
