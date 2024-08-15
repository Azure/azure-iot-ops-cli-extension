# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from rich.console import Console, NewLine
from rich.padding import Padding
from typing import Any, Dict, List, Optional, Tuple

from .check_manager import CheckManager
from ..common import ALL_NAMESPACES_TARGET, COLOR_STR_FORMAT, DEFAULT_PADDING, DEFAULT_PROPERTY_DISPLAY_COLOR
from ....common import CheckTaskStatus

logger = get_logger(__name__)


def add_display_and_eval(
    check_manager: CheckManager,
    target_name: str,
    display_text: str,
    eval_status: str,
    eval_value: str,
    resource_name: Optional[str] = None,
    namespace: str = ALL_NAMESPACES_TARGET,
    padding: Tuple[int, int, int, int] = (0, 0, 0, 8)
) -> None:
    check_manager.add_display(
        target_name=target_name,
        namespace=namespace,
        display=Padding(display_text, padding)
    )
    check_manager.add_target_eval(
        target_name=target_name,
        namespace=namespace,
        status=eval_status,
        value=eval_value,
        resource_name=resource_name
    )


# TODO: test + refactor
def display_as_list(console: Console, result: Dict[str, Any]) -> None:
    success_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    skipped_count: int = 0

    def _increment_summary(status: str) -> None:
        nonlocal success_count, warning_count, error_count, skipped_count
        if not status:
            return
        if status == CheckTaskStatus.success.value:
            success_count = success_count + 1
        elif status == CheckTaskStatus.warning.value:
            warning_count = warning_count + 1
        elif status == CheckTaskStatus.error.value:
            error_count = error_count + 1
        elif status == CheckTaskStatus.skipped.value:
            skipped_count = skipped_count + 1

    def _print_summary() -> None:
        from rich.panel import Panel

        success_content = f"[green]{success_count} check(s) succeeded.[/green]"
        warning_content = f"{warning_count} check(s) raised warnings."
        warning_content = (
            f"[green]{warning_content}[/green]" if not warning_count else f"[yellow]{warning_content}[/yellow]"
        )
        error_content = f"{error_count} check(s) raised errors."
        error_content = f"[green]{error_content}[/green]" if not error_count else f"[red]{error_content}[/red]"
        skipped_content = f"[bright_white]{skipped_count} check(s) were skipped[/bright_white]."
        content = f"{success_content}\n{warning_content}\n{error_content}\n{skipped_content}"
        console.print(Panel(content, title="Check Summary", expand=False))

    def _enumerate_displays(checks: List[Dict[str, dict]]) -> None:
        for check in checks:
            status = check.get("status")
            prefix_emoji = _get_emoji_from_status(status)
            console.print(Padding(f"{prefix_emoji} {check['description']}", (0, 0, 0, 4)))

            targets = check.get("targets", {})
            for type in targets:
                for namespace in targets[type]:
                    namespace_target = targets[type][namespace]
                    displays = namespace_target.get("displays", [])
                    status = namespace_target.get("status")
                    for (idx, disp) in enumerate(displays):
                        # display status indicator on each 'namespaced' grouping of displays
                        if all([idx == 0, namespace != ALL_NAMESPACES_TARGET, status]):
                            prefix_emoji = _get_emoji_from_status(status)
                            console.print(Padding(f"\n{prefix_emoji} {disp.renderable}", (0, 0, 0, 6)))
                        else:
                            console.print(disp)
                    target_status = targets[type][namespace].get("status")
                    evaluations = targets[type][namespace].get("evaluations", [])
                    if not evaluations:
                        _increment_summary(target_status)
                    for e in evaluations:
                        eval_status = e.get("status")
                        _increment_summary(eval_status)
            console.print(NewLine(1))
        console.print(NewLine(1))

    title: dict = result.get("title")
    if title:
        console.print(NewLine(1))
        console.rule(title, align="center", style="blue bold")
        console.print(NewLine(1))

    pre_checks: List[dict] = result.get("preDeployment")
    if pre_checks:
        console.rule("Pre deployment checks", align="left")
        console.print(NewLine(1))
        _enumerate_displays(pre_checks)

    post_checks: List[dict] = result.get("postDeployment")
    if post_checks:
        console.rule("Post deployment checks", align="left")
        console.print(NewLine(1))
        _enumerate_displays(post_checks)

    _print_summary()


def _get_emoji_from_status(status: str) -> str:
    return "" if not status else CheckTaskStatus.map_to_colored_emoji(status)


def process_value_color(
    check_manager: CheckManager,
    target_name: str,
    key: Any,
    value: Any,
) -> str:
    value = value if value else "N/A"
    if "error" in str(key).lower() and str(value).lower() not in ["null", "n/a", "none", "noerror"]:
        check_manager.set_target_status(
            target_name=target_name,
            status=CheckTaskStatus.error.value
        )
        return f"[red]{value}[/red]"
    return f"[cyan]{value}[/cyan]"


def colorize_string(value: str, color: Optional[str] = DEFAULT_PROPERTY_DISPLAY_COLOR) -> str:
    color = color or DEFAULT_PROPERTY_DISPLAY_COLOR
    return COLOR_STR_FORMAT.format(value=value, color=color)


def basic_property_display(
    label: str,
    value: str,
    color: Optional[str] = DEFAULT_PROPERTY_DISPLAY_COLOR,
    padding: Optional[int] = DEFAULT_PADDING
) -> Padding:
    padding = padding or DEFAULT_PADDING
    return Padding(
        f"{label}: {colorize_string(value=value, color=color)}",
        (0, 0, 0, padding)
    )
