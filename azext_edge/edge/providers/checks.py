# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import List, Optional
from rich.console import Console

from .check.bluefin import check_bluefin_deployment
from .check.e4k import check_e4k_deployment

console = Console(width=100, highlight=False)


def run_checks(
    edge_service: str = "e4k",
    extended: Optional[bool] = False,
    namespace: Optional[str] = None,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
    resource_kinds: List[str] = None,
):
    result = {}

    with console.status("Analyzing cluster..."):
        from time import sleep

        sleep(0.25)

        result["title"] = f"Evaluation for {{[bright_blue]{edge_service}[/bright_blue]}} edge service deployment"

        if edge_service == "e4k":
            result = check_e4k_deployment(
                extended=extended,
                namespace=namespace,
                pre_deployment=pre_deployment,
                post_deployment=post_deployment,
                result=result,
                as_list=as_list,
                resource_kinds=resource_kinds
            )
        elif edge_service == "bluefin":
            result = check_bluefin_deployment(
                extended=extended,
                namespace=namespace,
                pre_deployment=pre_deployment,
                post_deployment=post_deployment,
                result=result,
                as_list=as_list,
                resource_kinds=resource_kinds
            )

        if not as_list:
            return result
