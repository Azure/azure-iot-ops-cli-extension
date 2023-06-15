# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from pathlib import PurePath
from time import sleep
from typing import Dict, List, Optional, Union

from knack.log import get_logger
from rich.console import Console, NewLine

from .providers.base import load_config_context

logger = get_logger(__name__)

console = Console(width=120)



def check(
    cmd,
    pre_deployment_checks=None,
    post_deployment_checks=None,
    namespace=None,
    as_list=None,
    context_name=None,
):
    load_config_context(context_name=context_name)
    from .common import BROKER_RESOURCE
    from .providers.checks import run_checks
    return run_checks(as_list=as_list)


def check2(
    cmd,
    pre_deployment_checks=None,
    post_deployment_checks=None,
    namespace=None,
    as_list=None,
    context_name=None,
):
    if not as_list:
        logger.warning("Currently only --list mode is supported.")
        return

    load_config_context(context_name=context_name)
    from .common import BROKER_RESOURCE
    from .providers.base import get_cluster_custom_resources
    from .providers.e4i.support_bundle import build_bundle
    from .providers.stats import get_stats_pods

    get_cluster_custom_resources(BROKER_RESOURCE, raise_on_404=True)



    from azext_edge.e4k.common import CheckTaskStatus

    successful_tasks = []
    warning_tasks = []
    error_tasks = []
    skipped_tasks = []

    def print_summary():
        from rich.panel import Panel

        content = f"[green]{len(successful_tasks)} check(s) succeeded.[/green]"
        if warning_tasks:
            content = (
                content
                + "\n"
                + f"[yellow]{len(warning_tasks)} check(s) raised warnings.[/yellow]"
            )
        else:
            content = content + "\n" + "[green]0 check(s) raised warnings.[/green]"
        if error_tasks:
            content = (
                content
                + "\n"
                + f"[red]{len(error_tasks)} check(s) raised errors.[/red]"
            )
        else:
            content = content + "\n" + "[green]0 check(s) raised errors.[/green]"
        content = (
            content
            + "\n"
            + f"[grey84]{len(skipped_tasks)} check(s) were skipped.[/grey84]"
        )

        console.print(Panel(content, title="Summary", expand=False))

    def _handle_status(status: str):
        if status == CheckTaskStatus.success.value:
            successful_tasks.append(status)
        elif status == CheckTaskStatus.warning.value:
            warning_tasks.append(status)
        elif status == CheckTaskStatus.error.value:
            error_tasks.append(status)
        elif status == CheckTaskStatus.skipped.value:
            skipped_tasks.append(status)

    def handle_pre_deployment_checks():
        from azext_edge.e4k.providers.checks import pre_deployment_checks

        tasks = list(pre_deployment_checks.values())
        tasks.reverse()

        console.rule("Pre deployment checks", align="left")
        console.print(NewLine(1))
        with console.status("[cyan]Analyzing E4K environment...") as status:
            while tasks:
                task = tasks.pop()
                task_result = task()

                display = task_result.get("display")
                status = task_result.get("status")
                _handle_list_output(display)
                _handle_status(status)
                sleep(0.25)
                console.print(NewLine(1))
        console.print(NewLine(1))

    def handle_post_deployment_checks():
        from azext_edge.e4k.providers.checks import post_deployment_checks

        tasks = list(post_deployment_checks.values())
        tasks.reverse()

        console.rule("Post deployment checks", align="left")
        console.print(NewLine(1))
        with console.status("[cyan]Analyzing E4K environment...") as status:
            while tasks:
                task = tasks.pop()
                task_result = task()

                display = task_result.get("display")
                status = task_result.get("status")
                _handle_list_output(display)
                _handle_status(status)
                sleep(0.25)
                console.print(NewLine(1))
        console.print(NewLine(1))

    if not post_deployment_checks:
        handle_pre_deployment_checks()

    if pre_deployment_checks:
        print_summary()
        return

    handle_post_deployment_checks()
    print_summary()

    # console.print(NewLine(1))


def stats(
    cmd,
    namespace: str = None,
    refresh_in_seconds: int = 10,
    watch: Optional[bool] = None,
    context_name: Optional[str] = None,
):
    load_config_context(context_name=context_name)
    from .common import BROKER_RESOURCE
    from .providers.base import get_cluster_custom_resources
    from .providers.stats import get_stats_pods

    get_cluster_custom_resources(BROKER_RESOURCE, raise_on_404=True)

    return get_stats_pods(
        namespace=namespace, refresh_in_seconds=refresh_in_seconds, watch=watch
    )


def support_bundle(
    cmd,
    namespaces: list = None,
    bundle_dir: Optional[str] = None,
    context_name: Optional[str] = None,
):
    load_config_context(context_name=context_name)
    # TODO: Temp use of get_bundle_path in e4i space. Common
    # utility functions will be relocated.
    from .commands_e4i import get_bundle_path
    from .common import BROKER_RESOURCE
    from .providers.base import get_cluster_custom_resources
    from .providers.support_bundle import build_bundle

    get_cluster_custom_resources(resource=BROKER_RESOURCE, raise_on_404=True)

    bundle_path: PurePath = get_bundle_path(bundle_dir=bundle_dir, system_name="e4k")
    return build_bundle(bundle_path=str(bundle_path), namespaces=namespaces)


def config(cmd, passphrase: str, iterations: int = 210000):
    import base64
    from hashlib import pbkdf2_hmac
    from os import urandom

    dk = pbkdf2_hmac(
        "sha512", bytes(passphrase, encoding="utf8"), urandom(16), iterations
    )
    return {
        "hash": f"pbkdf2-sha512$i={iterations},l={len(dk)}${str(base64.b64encode(dk), encoding='utf-8')}"
    }


def _handle_list_output(display: Union[str, dict]):
    if isinstance(display, str):
        console.print(display, highlight=False)
    elif isinstance(display, dict):
        for k in display:
            console.print(k, highlight=False)
            for i in display[k]:
                console.print(i, highlight=False)
