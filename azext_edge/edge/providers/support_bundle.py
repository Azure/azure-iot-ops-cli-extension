# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import List, Optional
from zipfile import ZipFile, ZIP_DEFLATED

import yaml
from knack.log import get_logger
from rich.console import Console, NewLine

from ..common import SupportForEdgeServiceType
from ..providers.edge_api import (
    DATA_PROCESSOR_API_V1,
    MQ_API_V1A2,
    MQ_API_V1A3,
    MQ_API_V1A4,
    MQ_API_V1B1,
    LNM_API_V1B1,
    OPCUA_API_V1,
    SYMPHONY_API_V1,
    DEVICEREGISTRY_API_V1,
    EdgeApiManager,
)

logger = get_logger(__name__)

console = Console()

COMPAT_MQ_APIS = EdgeApiManager(resource_apis=[MQ_API_V1A2, MQ_API_V1A3, MQ_API_V1A4, MQ_API_V1B1])
COMPAT_OPCUA_APIS = EdgeApiManager(resource_apis=[OPCUA_API_V1])
COMPAT_DATA_PROCESSOR_APIS = EdgeApiManager(resource_apis=[DATA_PROCESSOR_API_V1])
COMPAT_SYMPHONY_APIS = EdgeApiManager(resource_apis=[SYMPHONY_API_V1])
COMPAT_LNM_APIS = EdgeApiManager(resource_apis=[LNM_API_V1B1])
COMPAT_DEVICEREGISTRY_APIS = EdgeApiManager(resource_apis=[DEVICEREGISTRY_API_V1])


def build_bundle(edge_service: str, bundle_path: str, log_age_seconds: Optional[int] = None):
    from rich.live import Live
    from rich.progress import Progress
    from rich.table import Table

    from .support.dataprocessor import prepare_bundle as prepare_dataprocessor_bundle
    from .support.mq import prepare_bundle as prepare_mq_bundle
    from .support.lnm import prepare_bundle as prepare_lnm_bundle
    from .support.opcua import prepare_bundle as prepare_opcua_bundle
    from .support.symphony import prepare_bundle as prepare_symphony_bundle
    from .support.deviceregistry import prepare_bundle as prepare_deviceregistry_bundle
    from .support.shared import prepare_bundle as prepare_shared_bundle

    pending_work = {
        "mq": {}, "opcua": {}, "dataprocessor": {}, "symphony": {}, "deviceregistry": {}, "common": {}, "lnm": {}
    }

    api_map = {
        SupportForEdgeServiceType.mq.value: {
            'apis': COMPAT_MQ_APIS, 'prepare_bundle': prepare_mq_bundle, 'key': 'mq'},
        SupportForEdgeServiceType.opcua.value: {
            'apis': COMPAT_OPCUA_APIS, 'prepare_bundle': prepare_opcua_bundle, 'key': 'opcua'},
        SupportForEdgeServiceType.dataprocessor.value: {
            'apis': COMPAT_DATA_PROCESSOR_APIS, 'prepare_bundle': prepare_dataprocessor_bundle, 'key': 'dataprocessor'},
        SupportForEdgeServiceType.symphony.value: {
            'apis': COMPAT_SYMPHONY_APIS, 'prepare_bundle': prepare_symphony_bundle, 'key': 'symphony'},
        SupportForEdgeServiceType.lnm.value: {
            'apis': COMPAT_LNM_APIS, 'prepare_bundle': prepare_lnm_bundle, 'key': 'lnm'},
        SupportForEdgeServiceType.deviceregistry.value: {
            'apis': COMPAT_DEVICEREGISTRY_APIS,
            'prepare_bundle': prepare_deviceregistry_bundle,
            'key': 'deviceregistry'
        }
    }

    raise_on_404 = not (edge_service == SupportForEdgeServiceType.auto.value)

    for service_type, api_info in api_map.items():
        if edge_service in [SupportForEdgeServiceType.auto.value, service_type]:
            deployed_apis = api_info['apis'].get_deployed(raise_on_404)
            if deployed_apis:
                bundle_method = api_info['prepare_bundle']
                # Check if the function takes a second argument
                if service_type == SupportForEdgeServiceType.deviceregistry.value:
                    bundle = bundle_method(deployed_apis)
                else:
                    bundle = bundle_method(deployed_apis, log_age_seconds)

                pending_work[api_info['key']].update(bundle)

    # @digimaun - consider combining this work check with work count.
    if not any(v for _, v in pending_work.items()):
        logger.warning("No known edge services discovered on cluster.")
        return

    pending_work["common"].update(prepare_shared_bundle())

    total_work_count = 0
    for service in pending_work:
        total_work_count = total_work_count + len(pending_work[service])

    bundle = {service: {} for service, _ in pending_work.items()}

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

        for service in pending_work:
            if pending_work[service]:
                visually_process(
                    description=f"Processing {service} resources",
                    support_segment=pending_work[service],
                    edge_service=service,
                )

    write_zip(file_path=bundle_path, bundle=bundle)
    return {"bundlePath": bundle_path}


def write_zip(bundle: dict, file_path: str):
    with ZipFile(file=file_path, mode="w", compression=ZIP_DEFLATED) as myzip:
        todo: List[dict] = []
        for edge_service in bundle:
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
