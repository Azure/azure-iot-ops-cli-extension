# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from platform import system
from typing import Dict, List, NamedTuple, Optional, Tuple

import requests
from azure.cli.core.azclierror import ValidationError
from azure.cli.core.extension import get_extension_path
from knack.log import get_logger
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Confirm

from ....constants import EXTENSION_NAME
from ...util.common import run_host_command
from .common import ARM_ENDPOINT, MCR_ENDPOINT, GRAPH_ENDPOINT

NFS_COMMON_ALIAS = "nfs-common"

logger = get_logger(__name__)
console = Console(width=88)


class EndpointConnections(NamedTuple):
    connect_map: Dict[str, bool]

    @property
    def failed_connections(self):
        fc = []
        for endpoint in self.connect_map:
            if not self.connect_map[endpoint]:
                fc.append(endpoint)
        return fc

    def throw_if_failure(self, include_cluster: bool = True):
        failed_conns = self.failed_connections
        if failed_conns:
            raise ValidationError(get_connectivity_error(failed_conns, include_cluster=include_cluster))


def run_host_verify(render_progress: Optional[bool] = True, confirm_yes: Optional[bool] = False):
    if not render_progress:
        console.quiet = True
    connect_endpoints = [ARM_ENDPOINT, MCR_ENDPOINT]
    console.print()

    with console.status(status="Analyzing host...") as status_render:
        console.print("[bold]Connectivity[/bold] to:")
        endpoint_connections = preflight_http_connections(connect_endpoints)
        for endpoint in endpoint_connections.connect_map:
            console.print(f"- {endpoint} ", "...", endpoint_connections.connect_map[endpoint])
        endpoint_connections.throw_if_failure()

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

                        from os import geteuid  # pylint: disable=no-name-in-module

                        if geteuid() != 0:
                            az_ext_dir = get_extension_path(EXTENSION_NAME)
                            if not az_ext_dir:
                                raise ValidationError(
                                    "Unable to determine extension directory. Please ensure extension installation."
                                )
                            # pylint: disable-next=unsubscriptable-object
                            az_ext_dir = az_ext_dir[: az_ext_dir.index(EXTENSION_NAME)]
                            raise ValidationError(
                                "sudo user not detected.\n\nPlease run the command in the following form:\n"
                                f"-> sudo AZURE_EXTENSION_DIR={az_ext_dir} az iot ops verify-host"
                            )

                    install_nfs_common_result = install_package(NFS_COMMON_ALIAS)
                    if install_nfs_common_result:
                        console.print(f"[cyan]{NFS_COMMON_ALIAS}[/cyan] installed succesfully!")

    console.print()


def check_connectivity(url: str, timeout: int = 20):
    try:
        req = requests.head(url=url, timeout=timeout)
        req.raise_for_status()
        return True
    except requests.HTTPError:
        # HTTPError implies an http server response
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
    endpoints: List[str], protocol: str = "https", direction: str = "outbound", include_cluster: bool = True
):
    todo_endpoints = []
    if endpoints:
        todo_endpoints.extend(endpoints)

    endpoints_list_format = ""
    for ep in todo_endpoints:
        endpoints_list_format += f"* {ep}\n"

    connectivity_error = (
        f"\nUnable to verify {direction} {protocol} connectivity to:\n"
        f"\n{endpoints_list_format}\n"
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


def preflight_http_connections(endpoints: List[str]) -> EndpointConnections:
    """
    Tests connectivity for each endpoint in the provided list.
    """
    todo_connect_endpoints = []
    if endpoints:
        todo_connect_endpoints.extend(endpoints)

    endpoint_connect_map = {}
    for endpoint in todo_connect_endpoints:
        endpoint_connect_map[endpoint] = check_connectivity(url=endpoint)

    return EndpointConnections(connect_map=endpoint_connect_map)


def verify_cli_client_connections(include_graph: bool):
    test_endpoints = [ARM_ENDPOINT]
    if include_graph:
        test_endpoints.append(GRAPH_ENDPOINT)
    preflight_http_connections(test_endpoints).throw_if_failure(include_cluster=False)
