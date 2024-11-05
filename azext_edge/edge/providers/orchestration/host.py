# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from typing import Dict, List, NamedTuple

import requests
from azure.cli.core.azclierror import ValidationError
from knack.log import get_logger
from rich.console import Console

from .common import ARM_ENDPOINT

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


def verify_cli_client_connections():
    test_endpoints = [ARM_ENDPOINT]
    preflight_http_connections(test_endpoints).throw_if_failure(include_cluster=False)
