# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from azure.core.exceptions import HttpResponseError

from azext_edge.edge.util.workflow_display import StepState, WorkflowDisplay, format_dot_leader, render_summary


class TestStepState:
    """StepState enum values."""

    def test_enum_values(self):
        assert StepState.PENDING.value == "pending"
        assert StepState.ACTIVE.value == "active"
        assert StepState.COMPLETE.value == "complete"
        assert StepState.SKIPPED.value == "skipped"
        assert StepState.FAILED.value == "failed"

    def test_all_states_present(self):
        assert len(StepState) == 5


SAMPLE_CATEGORIES = {
    "Analyzing": ["Step A", "Step B"],
    "Building": ["Step C", "Step D", "Step E"],
}


class TestWorkflowDisplayInit:
    """Constructor and initial state."""

    def test_initial_state_all_pending(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        for cat_steps in display._steps.values():
            for entry in cat_steps.values():
                assert entry[0] == StepState.PENDING
                assert entry[1] == ""

    def test_categories_preserve_order(self):
        cats = {"First": ["S1"], "Second": ["S2"], "Third": ["S3"]}
        display = WorkflowDisplay("Test", cats)
        assert list(display._steps.keys()) == ["First", "Second", "Third"]

    def test_steps_preserve_order(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        assert list(display._steps["Building"].keys()) == ["Step C", "Step D", "Step E"]

    def test_no_progress_flag_coercion(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES, no_progress=1)
        assert display._no_progress is True

    def test_console_uses_stderr(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        assert display._console.stderr is True


class TestUpdateStep:
    """State transitions via update_step()."""

    def test_pending_to_active(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        display.update_step("Analyzing", "Step A", StepState.ACTIVE)
        assert display._steps["Analyzing"]["Step A"] == [StepState.ACTIVE, ""]

    def test_active_to_complete_with_detail(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        display.update_step("Analyzing", "Step A", StepState.ACTIVE)
        display.update_step("Analyzing", "Step A", StepState.COMPLETE, "created")
        assert display._steps["Analyzing"]["Step A"] == [StepState.COMPLETE, "created"]

    def test_skipped_with_detail(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        display.update_step("Analyzing", "Step B", StepState.SKIPPED, "not needed")
        assert display._steps["Analyzing"]["Step B"] == [StepState.SKIPPED, "not needed"]

    def test_failed_with_detail(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        display.update_step("Building", "Step C", StepState.FAILED, "failed: timeout")
        assert display._steps["Building"]["Step C"] == [StepState.FAILED, "failed: timeout"]

    def test_unknown_category_raises(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        with pytest.raises(ValueError, match="Unknown category"):
            display.update_step("Nonexistent", "Step A", StepState.ACTIVE)

    def test_unknown_step_raises(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        with pytest.raises(ValueError, match="Unknown step"):
            display.update_step("Analyzing", "Nonexistent", StepState.ACTIVE)

    def test_no_progress_is_noop(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES, no_progress=True)
        # Should not raise even with invalid args — completely skipped
        display.update_step("Nonexistent", "Nope", StepState.ACTIVE)
        # State unchanged
        assert display._steps["Analyzing"]["Step A"][0] == StepState.PENDING


class TestCompleteCategory:
    """Bulk completion of pending steps."""

    def test_marks_pending_as_complete(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        display.update_step("Building", "Step C", StepState.COMPLETE, "created")
        display.complete_category("Building")
        assert display._steps["Building"]["Step C"] == [StepState.COMPLETE, "created"]
        assert display._steps["Building"]["Step D"] == [StepState.COMPLETE, "done"]
        assert display._steps["Building"]["Step E"] == [StepState.COMPLETE, "done"]

    def test_preserves_non_pending_states(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        display.update_step("Analyzing", "Step A", StepState.SKIPPED, "exists")
        display.update_step("Analyzing", "Step B", StepState.FAILED, "timeout")
        display.complete_category("Analyzing")
        # Non-pending states are untouched
        assert display._steps["Analyzing"]["Step A"] == [StepState.SKIPPED, "exists"]
        assert display._steps["Analyzing"]["Step B"] == [StepState.FAILED, "timeout"]

    def test_preserves_existing_detail_on_pending(self):
        """If a pending step already has a detail string, complete_category keeps it."""
        display = WorkflowDisplay("Test", {"Cat": ["S1"]})
        display._steps["Cat"]["S1"] = [StepState.PENDING, "pre-set"]
        display.complete_category("Cat")
        assert display._steps["Cat"]["S1"] == [StepState.COMPLETE, "pre-set"]

    def test_unknown_category_raises(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES)
        with pytest.raises(ValueError, match="Unknown category"):
            display.complete_category("Nonexistent")

    def test_no_progress_is_noop(self):
        display = WorkflowDisplay("Test", SAMPLE_CATEGORIES, no_progress=True)
        display.complete_category("Nonexistent")  # no error
        assert display._steps["Analyzing"]["Step A"][0] == StepState.PENDING


class TestRendering:
    """Grid rendering correctness."""

    def test_title_in_output(self):
        display = WorkflowDisplay("My Workflow Title", {"Cat": ["S1"]})
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "My Workflow Title" in output

    def test_category_names_in_output(self):
        display = WorkflowDisplay("Test", {"First Cat": ["S1"], "Second Cat": ["S2"]})
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "First Cat" in output
        assert "Second Cat" in output

    def test_pending_step_no_status_word(self):
        display = WorkflowDisplay("Test", {"Cat": ["My Step"]})
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "My Step" in output
        # No dots or status word for pending
        assert ".." not in output

    def test_active_step_shows_ellipsis(self):
        display = WorkflowDisplay("Test", {"Cat": ["My Step"]})
        display.update_step("Cat", "My Step", StepState.ACTIVE)
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "My Step ..." in output

    def test_complete_step_shows_dot_leaders_and_status(self):
        display = WorkflowDisplay("Test", {"Cat": ["My Step"]})
        display.update_step("Cat", "My Step", StepState.COMPLETE, "created")
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "My Step" in output
        assert "created" in output
        assert ".." in output  # dot leaders present

    def test_skipped_step_shows_detail(self):
        display = WorkflowDisplay("Test", {"Cat": ["My Step"]})
        display.update_step("Cat", "My Step", StepState.SKIPPED, "exists")
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "exists" in output
        assert ".." in output

    def test_failed_step_shows_detail(self):
        display = WorkflowDisplay("Test", {"Cat": ["My Step"]})
        display.update_step("Cat", "My Step", StepState.FAILED, "failed: 403")
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "failed: 403" in output

    def test_no_progress_footer_transient(self):
        """Transient displays omit the animated progress footer."""
        display = WorkflowDisplay("Test", {"Cat": ["S1"]}, transient=True)
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "Elapsed" not in output
        assert "Working" not in output

    def test_progress_footer_non_transient(self, mocker):
        """Non-transient displays include animated progress bar with elapsed time."""
        mocker.patch("azext_edge.edge.util.workflow_display.Live")
        display = WorkflowDisplay("Test", {"Cat": ["S1"]}, transient=False)
        with display:
            grid = display._render()
            output = _render_grid_to_text(grid)
            assert "Working..." in output
            assert "Elapsed:" in output

    def test_complete_detail_defaults_to_state_value(self):
        """When no detail is passed, the status word falls back to state.value."""
        display = WorkflowDisplay("Test", {"Cat": ["My Step"]})
        display.update_step("Cat", "My Step", StepState.COMPLETE)
        grid = display._render()
        output = _render_grid_to_text(grid)
        assert "complete" in output  # StepState.COMPLETE.value


class TestCategoryStyle:
    """Category header styling rules."""

    @pytest.mark.parametrize(
        "steps, expected_style",
        [
            # All pending → dim
            ({"S1": (StepState.PENDING, ""), "S2": (StepState.PENDING, "")}, "dim"),
            # Any active → cyan
            ({"S1": (StepState.COMPLETE, "done"), "S2": (StepState.ACTIVE, "")}, "cyan"),
            # All complete → default
            ({"S1": (StepState.COMPLETE, "done"), "S2": (StepState.COMPLETE, "done")}, ""),
            # All skipped → default
            ({"S1": (StepState.SKIPPED, "exists")}, ""),
            # Mix of complete and skipped → default
            ({"S1": (StepState.COMPLETE, "done"), "S2": (StepState.SKIPPED, "exists")}, ""),
            # Any failed → red (takes priority over active)
            ({"S1": (StepState.FAILED, "err"), "S2": (StepState.ACTIVE, "")}, "red"),
            # Mix of complete and pending → cyan (in progress)
            ({"S1": (StepState.COMPLETE, "done"), "S2": (StepState.PENDING, "")}, "cyan"),
        ],
    )
    def test_category_style_rules(self, steps, expected_style):
        assert WorkflowDisplay._category_style(steps) == expected_style


class TestContextManager:
    """Context manager lifecycle."""

    def test_enter_creates_live_session(self, mocker):
        mock_live = MagicMock()
        mock_live_cls = mocker.patch("azext_edge.edge.util.workflow_display.Live", return_value=mock_live)

        display = WorkflowDisplay("Test", {"Cat": ["S1"]})
        with display:
            mock_live_cls.assert_called_once()
            call_kwargs = mock_live_cls.call_args.kwargs
            assert call_kwargs["transient"] is True
            assert call_kwargs["refresh_per_second"] == 8
            # Console passed is our stderr console
            assert call_kwargs["console"] is display._console
            mock_live.__enter__.assert_called_once()

    def test_exit_stops_live_session(self, mocker):
        mock_live = MagicMock()
        mocker.patch("azext_edge.edge.util.workflow_display.Live", return_value=mock_live)

        display = WorkflowDisplay("Test", {"Cat": ["S1"]})
        with display:
            pass

        mock_live.__exit__.assert_called_once_with(None, None, None)
        assert display._live is None

    def test_exit_without_enter_is_safe(self, mocker):
        mocker.patch("azext_edge.edge.util.workflow_display.Live")
        display = WorkflowDisplay("Test", {"Cat": ["S1"]})
        display.__exit__(None, None, None)  # no error

    def test_no_progress_skips_live(self):
        display = WorkflowDisplay("Test", {"Cat": ["S1"]}, no_progress=True)
        with display:
            assert display._live is None

    def test_non_transient_passes_flag(self, mocker):
        mock_live = MagicMock()
        mock_live_cls = mocker.patch("azext_edge.edge.util.workflow_display.Live", return_value=mock_live)

        display = WorkflowDisplay("Test", {"Cat": ["S1"]}, transient=False)
        with display:
            call_kwargs = mock_live_cls.call_args.kwargs
            assert call_kwargs["transient"] is False

    def test_get_renderable_override(self, mocker):
        """Live's get_renderable is overridden to call _render() on each refresh."""
        mock_live = MagicMock()
        mocker.patch("azext_edge.edge.util.workflow_display.Live", return_value=mock_live)

        display = WorkflowDisplay("Test", {"Cat": ["S1"]})
        with display:
            assert mock_live.get_renderable == display._render

    def test_transient_skips_progress_bar(self, mocker):
        """Transient displays do not create a Progress bar."""
        mocker.patch("azext_edge.edge.util.workflow_display.Live")

        display = WorkflowDisplay("Test", {"Cat": ["S1"]}, transient=True)
        with display:
            assert display._progress_bar is None
            assert display._task_id is None

    def test_non_transient_creates_progress_bar(self, mocker):
        """Non-transient displays create a Progress bar with a working task."""
        mocker.patch("azext_edge.edge.util.workflow_display.Live")

        display = WorkflowDisplay("Test", {"Cat": ["S1"]}, transient=False)
        with display:
            assert display._progress_bar is not None
            assert display._task_id is not None
            assert display._progress_bar.tasks[0].description == "Working..."

    def test_progress_bar_done_on_exit(self, mocker):
        """Non-transient displays update progress description to 'Done.' on exit."""
        mocker.patch("azext_edge.edge.util.workflow_display.Live")

        display = WorkflowDisplay("Test", {"Cat": ["S1"]}, transient=False)
        with display:
            pass
        task = display._progress_bar.tasks[0]
        assert task.description == "Done."
        assert task.stop_time is not None


class TestStepScope:
    """step_scope() context manager behavior."""

    def test_sets_active_on_enter(self):
        """Entering step_scope sets the step to ACTIVE."""
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with display.step_scope("Cat", "Step"):
            assert display._steps["Cat"]["Step"][0] == StepState.ACTIVE

    def test_clean_exit_preserves_state(self):
        """Clean exit does not change state — caller is responsible for COMPLETE/SKIPPED."""
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with display.step_scope("Cat", "Step"):
            pass
        # State stays ACTIVE because caller didn't set COMPLETE/SKIPPED
        assert display._steps["Cat"]["Step"][0] == StepState.ACTIVE

    def test_exception_sets_failed_and_reraises(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with pytest.raises(RuntimeError, match="boom"):
            with display.step_scope("Cat", "Step"):
                raise RuntimeError("boom")
        assert display._steps["Cat"]["Step"][0] == StepState.FAILED
        assert display._steps["Cat"]["Step"][1] == "boom"

    def test_failed_detail_truncated_to_40_chars(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        long_msg = "A" * 60
        with pytest.raises(RuntimeError):
            with display.step_scope("Cat", "Step"):
                raise RuntimeError(long_msg)
        assert display._steps["Cat"]["Step"][1] == "A" * 40
        assert len(display._steps["Cat"]["Step"][1]) == 40

    def test_caller_sets_complete_inside_scope(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with display.step_scope("Cat", "Step"):
            display.update_step("Cat", "Step", StepState.COMPLETE, "created")
        assert display._steps["Cat"]["Step"] == [StepState.COMPLETE, "created"]

    def test_caller_sets_skipped_inside_scope(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with display.step_scope("Cat", "Step"):
            display.update_step("Cat", "Step", StepState.SKIPPED, "exists")
        assert display._steps["Cat"]["Step"] == [StepState.SKIPPED, "exists"]

    def test_exception_overwrites_prior_complete(self):
        """If caller sets COMPLETE then an exception fires, FAILED wins."""
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with pytest.raises(ValueError):
            with display.step_scope("Cat", "Step"):
                display.update_step("Cat", "Step", StepState.COMPLETE, "ok")
                raise ValueError("late failure")
        assert display._steps["Cat"]["Step"][0] == StepState.FAILED
        assert display._steps["Cat"]["Step"][1] == "late failure"

    def test_no_progress_mode_still_executes_body(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step"]}, no_progress=True)
        executed = False
        with display.step_scope("Cat", "Step"):
            executed = True
        assert executed
        # State unchanged due to no_progress
        assert display._steps["Cat"]["Step"][0] == StepState.PENDING

    def test_no_progress_exception_still_reraises(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step"]}, no_progress=True)
        with pytest.raises(RuntimeError, match="boom"):
            with display.step_scope("Cat", "Step"):
                raise RuntimeError("boom")
        # State unchanged — update_step is a no-op in no_progress mode
        assert display._steps["Cat"]["Step"][0] == StepState.PENDING

    def test_unknown_category_raises_on_enter(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with pytest.raises(ValueError, match="Unknown category"):
            with display.step_scope("Bad", "Step"):
                pass

    def test_unknown_step_raises_on_enter(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with pytest.raises(ValueError, match="Unknown step"):
            with display.step_scope("Cat", "Bad"):
                pass

    @pytest.mark.parametrize(
        "exc_type",
        [RuntimeError, ValueError, HttpResponseError, TypeError],
        ids=["runtime", "value", "http_response", "type"],
    )
    def test_various_exception_types(self, exc_type):
        """step_scope catches all Exception subclasses, not just specific types."""
        display = WorkflowDisplay("Test", {"Cat": ["Step"]})
        with pytest.raises(exc_type):
            with display.step_scope("Cat", "Step"):
                if exc_type == HttpResponseError:
                    raise exc_type("test error", response=MagicMock(status_code=403))
                raise exc_type("test error")
        assert display._steps["Cat"]["Step"][0] == StepState.FAILED


class TestThreadSafety:
    """Concurrent update_step calls from multiple threads."""

    def test_concurrent_updates_no_crash(self):
        categories = {"Cat": [f"Step {i}" for i in range(20)]}
        display = WorkflowDisplay("Test", categories)

        errors = []

        def update_step(step_name: str) -> None:
            try:
                display.update_step("Cat", step_name, StepState.ACTIVE)
                display.update_step("Cat", step_name, StepState.COMPLETE, "done")
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(update_step, f"Step {i}") for i in range(20)]
            for f in futures:
                f.result()

        assert not errors
        # All steps should be complete
        for entry in display._steps["Cat"].values():
            assert entry[0] == StepState.COMPLETE

    def test_concurrent_render_and_update(self):
        """Render and update can run concurrently without data corruption."""
        categories = {"Cat": [f"Step {i}" for i in range(10)]}
        display = WorkflowDisplay("Test", categories)

        errors = []
        stop_event = threading.Event()

        def render_loop() -> None:
            try:
                while not stop_event.is_set():
                    display._render()
            except Exception as e:
                errors.append(e)

        def update_loop() -> None:
            try:
                for i in range(10):
                    display.update_step("Cat", f"Step {i}", StepState.ACTIVE)
                    display.update_step("Cat", f"Step {i}", StepState.COMPLETE, "done")
            except Exception as e:
                errors.append(e)

        render_thread = threading.Thread(target=render_loop)
        render_thread.start()

        update_loop()
        stop_event.set()
        render_thread.join(timeout=2)

        assert not errors


class TestDotLeaderLayout:
    """Dot-leader alignment and width calculations."""

    def test_dot_leader_present(self):
        display = WorkflowDisplay("Test", {"Cat": ["Step Name"]})
        text = display._render_step("Step Name", StepState.COMPLETE, "done")
        plain = text.plain
        assert " . " not in plain or ".." in plain  # dots are contiguous
        assert "Step Name" in plain
        assert "done" in plain

    def test_consistent_width(self):
        """All completed steps should produce lines of the same total width."""
        display = WorkflowDisplay("Test", {"Cat": ["Short", "A Much Longer Step Name"]})
        text1 = display._render_step("Short", StepState.COMPLETE, "done")
        text2 = display._render_step("A Much Longer Step Name", StepState.COMPLETE, "done")
        # Both lines should be the same length (DISPLAY_WIDTH)
        assert len(text1.plain) == len(text2.plain)

    def test_minimum_dots(self):
        """Very long name + status still gets at least 2 dots."""
        long_name = "A" * 45
        display = WorkflowDisplay("Test", {"Cat": [long_name]})
        text = display._render_step(long_name, StepState.COMPLETE, "done")
        plain = text.plain
        # Should contain at least ".." surrounded by spaces
        assert " .. " in plain


def _render_grid_to_text(grid) -> str:
    """Render a Rich renderable to plain text for assertion."""
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=120, no_color=True).print(grid)
    return buf.getvalue()


class TestFormatDotLeader:
    """Unit tests for format_dot_leader() module function."""

    def test_basic_output(self):
        line = format_dot_leader("Topic space", "created")
        assert line.startswith("    Topic space")
        assert line.endswith("created")
        assert ".." in line

    def test_consistent_width(self):
        """Different name lengths produce same total line width when detail is same length."""
        line1 = format_dot_leader("Short", "done")
        line2 = format_dot_leader("A Much Longer Step Name", "done")
        assert len(line1) == len(line2)

    def test_minimum_dots(self):
        """Very long name + detail still gets at least 2 dots."""
        long_name = "A" * 45
        line = format_dot_leader(long_name, "done")
        assert " .. " in line

    def test_custom_width(self):
        line = format_dot_leader("Step", "ok", width=30)
        # 30 - 4 (indent) - 4 (Step) - 2 (ok) - 2 (spaces) = 18 dots
        assert len(line) == 30

    def test_custom_indent(self):
        line = format_dot_leader("Step", "ok", indent="  ")
        assert line.startswith("  Step")

    def test_custom_dot_char(self):
        line = format_dot_leader("Step", "ok", dot_char="-")
        assert "--" in line
        assert ".." not in line


class TestRenderSummary:
    """Unit tests for render_summary() module function."""

    @staticmethod
    def _call_and_capture(mocker, sections, title="Title", footer=""):
        """Call render_summary() with a mocked Console and return the plain-text output."""
        mock_console = MagicMock()
        mocker.patch("azext_edge.edge.util.workflow_display.Console", return_value=mock_console)
        render_summary(title, sections, footer=footer)
        grid = mock_console.print.call_args[0][0]
        return _render_grid_to_text(grid)

    def test_basic_render(self, mocker):
        """Renders title, sections with items, and footer."""
        mock_console = MagicMock()
        mock_console_cls = mocker.patch(
            "azext_edge.edge.util.workflow_display.Console", return_value=mock_console,
        )

        sections = {
            "Category A": [("Item 1", "detail1"), ("Item 2", "detail2")],
            "Category B": [("Item 3", "detail3")],
        }
        render_summary("Test Title", sections, footer="A footer note.")

        mock_console_cls.assert_called_once_with(stderr=True)
        mock_console.print.assert_called_once()
        output = _render_grid_to_text(mock_console.print.call_args[0][0])

        assert "Test Title" in output
        assert "Category A" in output
        assert "Category B" in output
        assert "Item 1" in output
        assert "detail1" in output
        assert "Item 3" in output
        assert "A footer note." in output

    def test_empty_sections_skipped(self, mocker):
        """Empty item lists are silently skipped."""
        sections = {
            "Has Items": [("Item", "detail")],
            "Empty": [],
        }
        output = self._call_and_capture(mocker, sections)

        assert "Has Items" in output
        assert "Empty" not in output

    def test_all_empty_shows_fallback(self, mocker):
        """When all sections are empty, shows fallback message."""
        output = self._call_and_capture(mocker, {"A": [], "B": []})
        assert "No resources found." in output

    def test_no_footer(self, mocker):
        """No footer when not provided."""
        output = self._call_and_capture(mocker, {"Cat": [("Item", "detail")]})

        # Footer area should not contain extra content beyond the sections
        lines = [line for line in output.strip().split("\n") if line.strip()]
        # Title + Category + Item = at least 3 non-empty lines, no footer
        assert all("Note" not in line for line in lines)

    def test_plain_string_items(self, mocker):
        """Sections with plain string items render as simple indented lines."""
        sections = {
            "Category A": ["Item 1", "Item 2"],
            "Category B": ["Item 3"],
        }
        output = self._call_and_capture(mocker, sections, title="Title (3)")

        assert "Title (3)" in output
        assert "Category A" in output
        assert "Item 1" in output
        assert "Item 2" in output
        assert "Item 3" in output
        # Plain items should NOT have dot-leaders
        assert "..." not in output

    def test_mixed_item_types(self, mocker):
        """Sections can mix tuple items (dot-leaders) and string items (plain)."""
        sections = {
            "Tuples": [("Name", "detail")],
            "Strings": ["Plain item"],
        }
        output = self._call_and_capture(mocker, sections, title="Mixed")

        assert "Name" in output
        assert "detail" in output
        assert "Plain item" in output
