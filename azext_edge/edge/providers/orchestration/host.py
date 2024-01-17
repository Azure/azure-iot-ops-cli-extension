# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from platform import system
from typing import Optional, Tuple, List

import requests
from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger
from rich.console import Console
from rich.prompt import Confirm
from rich.markdown import Markdown

from ...util.common import run_host_command

ARM_ENDPOINT = "https://management.azure.com/"
MCR_ENDPOINT = "https://mcr.microsoft.com/api/v1/"

NFS_COMMON_ALIAS = "nfs-common"

logger = get_logger(__name__)
console = Console(width=88)


def run_host_checks(render_progress: bool = True, confirm_yes: bool = False):
    if not render_progress:
        console.quiet = True
    connect_tuples = [(ARM_ENDPOINT, "HEAD"), (MCR_ENDPOINT, "GET")]
    connect_result_map = {}
    console.print()

    with console.status(status="Analyzing host...", refresh_per_second=12.5) as status_render:
        console.print("[bold]Connectivity[/bold] to:")
        for connect_tuple in connect_tuples:
            connect_result_map[connect_tuple] = check_connectivity(url=connect_tuple[0], http_verb=connect_tuple[1])
            console.print(f"- {connect_tuple[0]} ", "...", connect_result_map[connect_tuple])
            if not connect_result_map[connect_tuple]:
                raise ValidationError(get_connectivity_error(connect_tuple[0]))

        if not is_windows():
            if is_ubuntu_distro():
                logger.debug("Determined the OS is Ubuntu.")
                console.print()
                console.print("OS eval for [bold]Ubuntu[/bold]:")
                is_nfs_common_installed = is_package_installed(NFS_COMMON_ALIAS)
                console.print(
                    f"- Is [cyan]{NFS_COMMON_ALIAS}[/cyan] installed?",
                    "...",
                    _get_eval_result_display(is_nfs_common_installed),
                )

                if is_nfs_common_installed is None:
                    status_render.stop()
                    logger.warning("Unable to determine if nfs-common is installed!")

                elif is_nfs_common_installed is False:
                    if not confirm_yes:
                        status_render.stop()
                        nfs_install_commands = get_package_install_commands(NFS_COMMON_ALIAS)
                        usr_script = "\n".join(nfs_install_commands)
                        console.print("\nInstall with the following commands?")
                        console.print(Markdown(f"```\n{usr_script}\n```"))
                        execute_install = Confirm.ask("(sudo required)")
                        if not execute_install:
                            raise ValidationError("Dependency install cancelled!")

                    install_nfs_common_result = install_package(NFS_COMMON_ALIAS)
                    if install_nfs_common_result:
                        console.print(f"[cyan]{NFS_COMMON_ALIAS}[/cyan] installed succesfully!")

    console.print()


def check_connectivity(url: str, timeout: int = 10, http_verb: str = "GET"):
    try:
        http_verb = http_verb.lower()
        if http_verb == "get":
            req = requests.get(url, timeout=timeout)
        if http_verb == "head":
            req = requests.head(url, timeout=timeout)

        req.raise_for_status()
        return True
    except requests.HTTPError:
        return True
    except requests.ConnectionError:
        return False


def is_ubuntu_distro() -> Optional[bool]:
    result = run_host_command("lsb_release -a")
    if not result or result.returncode != 0:
        return None

    kpis = result.stdout.decode(encoding="utf8").split("\n")
    for kpi in kpis:
        k = kpi.split("\t")
        if "distributor" in k[0].lower():
            if "ubuntu" in k[1].lower():
                return True

    return False


def is_package_installed(package_name: str) -> Optional[bool]:
    result = run_host_command(f"dpkg-query --show -f='${{Status}}' {package_name}")
    if result is None:
        return None

    if result.returncode == 0:
        kpis = result.stdout.decode(encoding="utf8").split("\n")
        if kpis and kpis[0] == "install ok installed":
            return True

    return False


def get_package_install_commands(package_name: str) -> List[str]:
    return ["apt-get update", f"apt-get install {package_name} -y"]


def install_package(package_name: str) -> bool:
    for command in get_package_install_commands(package_name):
        success, error = _run_command(command)
        if success is None:
            raise ValidationError("Unable to determine if package was installed.")
        if success is False:
            raise ValidationError(error)

    return True


def is_windows():
    return system().lower() == "windows"


def _run_command(command: str) -> Tuple[Optional[bool], Optional[str]]:
    result = run_host_command(command)
    if result is None:
        return None, None

    if result.returncode == 0:
        return True, None

    return False, result.stderr.decode("utf8")


def _get_eval_result_display(eval_result: Optional[bool]) -> str:
    if eval_result is None:
        return "???"
    return str(eval_result)


def get_connectivity_error(
    endpoint: str, protocol: str = "https", direction: str = "outbound", include_cluster: bool = True
):
    connectivity_error = (
        f"\nUnable to verify {direction} {protocol} connectivity to {endpoint}.\n"
        "Ensure host, proxy and/or firewall config allows connection.\n"
        "\nThe 'HTTP_PROXY' and 'HTTPS_PROXY' environment variables can be used for the CLI client.\n"
    )

    if not include_cluster:
        return connectivity_error

    connectivity_error += (
        "\nPlease ensure the cluster has connectivity. See the following for more details:\n"
        "https://learn.microsoft.com/en-us/azure/azure-arc/network-requirements-consolidated\n"
    )

    return connectivity_error
