# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import List, Optional
from zipfile import ZipFile

import yaml
from knack.log import get_logger
from rich.console import Console, NewLine

from ..common import SupportForEdgeServiceType
from ..providers.edge_api import BLUEFIN_API_V1, E4K_API_V1A2, E4K_API_V1A3, OPCUA_API_V1, EdgeApiManager

logger = get_logger(__name__)

console = Console()

COMPAT_E4K_APIS = EdgeApiManager(ResourceApis=[E4K_API_V1A2, E4K_API_V1A3])
COMPAT_OPCUA_APIS = EdgeApiManager(ResourceApis=[OPCUA_API_V1])
COMPAT_BLUEFIN_APIS = EdgeApiManager(ResourceApis=[BLUEFIN_API_V1])


def build_bundle(edge_service: str, bundle_path: str, log_age_seconds: Optional[int] = None):
    from rich.live import Live
    from rich.progress import Progress
    from rich.table import Table

    from .support.bluefin import prepare_bundle as prepare_bluefin_bundle
    from .support.e4k import prepare_bundle as prepare_e4k_bundle
    from .support.opcua import prepare_bundle as prepare_opcua_bundle
    from .support.shared import prepare_bundle as prepare_shared_bundle

    pending_work = {"e4k": {}, "opcua": {}, "bluefin": {}, "common": {}}

    raise_on_404 = not (edge_service == SupportForEdgeServiceType.auto.value)
    if edge_service in [SupportForEdgeServiceType.auto.value, SupportForEdgeServiceType.e4k.value]:
        e4k_apis = COMPAT_E4K_APIS.get_deployed(raise_on_404)
        if e4k_apis:
            pending_work["e4k"].update(prepare_e4k_bundle(e4k_apis, log_age_seconds))
    if edge_service in [SupportForEdgeServiceType.auto.value, SupportForEdgeServiceType.opcua.value]:
        opcua_apis = COMPAT_OPCUA_APIS.get_deployed(raise_on_404)
        if opcua_apis:
            pending_work["opcua"].update(prepare_opcua_bundle(opcua_apis, log_age_seconds))
    if edge_service in [SupportForEdgeServiceType.auto.value, SupportForEdgeServiceType.bluefin.value]:
        bluefin_apis = COMPAT_BLUEFIN_APIS.get_deployed(raise_on_404)
        if bluefin_apis:
            pending_work["bluefin"].update(prepare_bluefin_bundle(bluefin_apis, log_age_seconds))

    if not any([pending_work["e4k"], pending_work["opcua"], pending_work["bluefin"]]):
        logger.warning("No known edge services discovered on cluster.")
        return

    pending_work["common"].update(prepare_shared_bundle())
    total_work_count = (
        len(pending_work["opcua"])
        + len(pending_work["e4k"])
        + len(pending_work["bluefin"])
        + len(pending_work["common"])
    )

    bundle = {"e4k": {}, "opcua": {}, "bluefin": {}, "common": {}}
    grid = Table.grid(expand=False)
    with Live(grid, console=console, transient=True) as live:
        uber_progress = Progress()
        uber_task = uber_progress.add_task(
            "[green]Building support bundle",
            total=total_work_count,
        )

        def visually_process(description: str, support_segment: dict, edge_service: str):
            namespace_task = uber_progress.add_task(f"[cyan]{description}", total=len(support_segment))
            for element in support_segment:
                header = f"Fetching [medium_purple4]{element}[/medium_purple4] data..."
                grid = Table.grid(expand=False)
                grid.add_column()

                grid.add_row(NewLine(1))
                grid.add_row(header)
                grid.add_row(NewLine(1))
                grid.add_row(uber_progress)
                live.update(grid, refresh=True)

                try:
                    # Produce as much support collateral as possible.
                    bundle[edge_service][element] = support_segment[element]()
                except Exception as e:
                    # @digimaun - bdb.BdbQuit?
                    logger.debug(f"Unable to process {edge_service} {element}:\n{e}")

                if not uber_progress.finished:
                    uber_progress.update(namespace_task, advance=1)
                    uber_progress.update(uber_task, advance=1)

        if pending_work["e4k"]:
            visually_process(
                description="Processing E4K resources",
                support_segment=pending_work["e4k"],
                edge_service="e4k",
            )
        if pending_work["opcua"]:
            visually_process(
                description="Processing OPC-UA resources",
                support_segment=pending_work["opcua"],
                edge_service="opcua",
            )
        if pending_work["bluefin"]:
            visually_process(
                description="Processing Bluefin resources",
                support_segment=pending_work["bluefin"],
                edge_service="bluefin",
            )
        if pending_work["common"]:
            visually_process(
                description="Processing common resources", support_segment=pending_work["common"], edge_service="common"
            )

    write_zip(file_path=bundle_path, bundle=bundle)
    return {"bundlePath": bundle_path}


def write_zip(bundle: dict, file_path: str):
    with ZipFile(file=file_path, mode="w") as myzip:
        todo: List[dict] = []
        for edge_service in ["e4k", "opcua", "bluefin", "common"]:
            if edge_service in bundle:
                for element in bundle[edge_service]:
                    if isinstance(bundle[edge_service][element], list):
                        todo.extend(bundle[edge_service][element])
                    else:
                        todo.append(bundle[edge_service][element])

        added_path = {}
        for t in todo:
            if t:
                data = t.get("data")
                zinfo = t.get("zinfo")
                if data and zinfo not in added_path:
                    if isinstance(data, dict):
                        data = yaml.safe_dump(t["data"], indent=2)
                    myzip.writestr(zinfo_or_arcname=zinfo, data=data)
                    added_path[zinfo] = True


def str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.representer.SafeRepresenter.add_representer(str, str_presenter)
