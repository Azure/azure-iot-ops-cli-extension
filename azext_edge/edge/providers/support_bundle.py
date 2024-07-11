# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional
from zipfile import ZipFile, ZIP_DEFLATED

import yaml
from knack.log import get_logger
from rich.console import Console, NewLine

from ..common import OpsServiceType
from ..providers.edge_api import (
    CLUSTER_CONFIG_API_V1,
    MQTT_BROKER_API_V1B1,
    OPCUA_API_V1,
    ORC_API_V1,
    AKRI_API_V0,
    DEVICEREGISTRY_API_V1,
    DATAFLOW_API_V1B1,
    EdgeApiManager,
)

logger = get_logger(__name__)

console = Console()

COMPAT_CLUSTER_CONFIG_APIS = EdgeApiManager(resource_apis=[CLUSTER_CONFIG_API_V1])
COMPAT_MQTT_BROKER_APIS = EdgeApiManager(resource_apis=[MQTT_BROKER_API_V1B1])
COMPAT_OPCUA_APIS = EdgeApiManager(resource_apis=[OPCUA_API_V1])
COMPAT_ORC_APIS = EdgeApiManager(resource_apis=[ORC_API_V1])
COMPAT_AKRI_APIS = EdgeApiManager(resource_apis=[AKRI_API_V0])
COMPAT_DEVICEREGISTRY_APIS = EdgeApiManager(resource_apis=[DEVICEREGISTRY_API_V1])
COMPAT_DATAFLOW_APIS = EdgeApiManager(resource_apis=[DATAFLOW_API_V1B1])


def build_bundle(
    ops_service: str,
    bundle_path: str,
    log_age_seconds: Optional[int] = None,
    include_arc_agents: Optional[bool] = None,
    include_mq_traces: Optional[bool] = None,
):
    from rich.live import Live
    from rich.progress import Progress
    from rich.table import Table

    from .support.mq import prepare_bundle as prepare_mq_bundle
    from .support.opcua import prepare_bundle as prepare_opcua_bundle
    from .support.orc import prepare_bundle as prepare_symphony_bundle
    from .support.dataflow import prepare_bundle as prepare_dataflow_bundle
    from .support.deviceregistry import prepare_bundle as prepare_deviceregistry_bundle
    from .support.shared import prepare_bundle as prepare_shared_bundle
    from .support.akri import prepare_bundle as prepare_akri_bundle
    from .support.otel import prepare_bundle as prepare_otel_bundle
    from .support.arcagents import prepare_bundle as prepare_arcagents_bundle

    pending_work = {k: {} for k in OpsServiceType.list()}
    pending_work.pop(OpsServiceType.auto.value)

    api_map = {
        # TODO: re-enable billing once service is available post 0.6.0 release
        # OpsServiceType.billing.value: {"apis": COMPAT_CLUSTER_CONFIG_APIS, "prepare_bundle": prepare_billing_bundle},
        OpsServiceType.mq.value: {"apis": COMPAT_MQTT_BROKER_APIS, "prepare_bundle": prepare_mq_bundle},
        OpsServiceType.opcua.value: {
            "apis": COMPAT_OPCUA_APIS,
            "prepare_bundle": prepare_opcua_bundle,
        },
        OpsServiceType.orc.value: {
            "apis": COMPAT_ORC_APIS,
            "prepare_bundle": prepare_symphony_bundle,
        },
        OpsServiceType.akri.value: {"apis": COMPAT_AKRI_APIS, "prepare_bundle": prepare_akri_bundle},
        OpsServiceType.deviceregistry.value: {
            "apis": COMPAT_DEVICEREGISTRY_APIS,
            "prepare_bundle": prepare_deviceregistry_bundle,
        },
        OpsServiceType.dataflow.value: {"apis": COMPAT_DATAFLOW_APIS, "prepare_bundle": prepare_dataflow_bundle},
    }

    raise_on_404 = not (ops_service == OpsServiceType.auto.value)

    for service_moniker, api_info in api_map.items():
        if ops_service in [OpsServiceType.auto.value, service_moniker]:
            deployed_apis = api_info["apis"].get_deployed(raise_on_404)
            if deployed_apis:
                bundle_method = api_info["prepare_bundle"]
                # Check if the function takes a second argument
                # TODO: Change to kwargs based pattern
                if service_moniker == OpsServiceType.deviceregistry.value:
                    bundle = bundle_method(deployed_apis)
                elif service_moniker == OpsServiceType.mq.value:
                    bundle = bundle_method(deployed_apis, log_age_seconds, include_mq_traces)
                else:
                    bundle = bundle_method(deployed_apis, log_age_seconds)

                pending_work[service_moniker].update(bundle)

    # arc agent resources
    if include_arc_agents:
        pending_work["arcagents"] = prepare_arcagents_bundle(log_age_seconds)

    # @digimaun - consider combining this work check with work count.
    if not any(v for _, v in pending_work.items()):
        logger.warning("No known IoT Operations services discovered on cluster.")
        return

    if ops_service == OpsServiceType.auto.value:
        # Only attempt to collect otel resources if any AIO service is deployed AND auto is used.
        pending_work["otel"] = prepare_otel_bundle()

    # Collect common resources if any AIO service is deployed with any service selected.
    pending_work["common"] = prepare_shared_bundle()

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

        def visually_process(description: str, support_segment: dict, ops_service: str):
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
                    bundle[ops_service][element] = support_segment[element]()
                except Exception as e:
                    # @digimaun - bdb.BdbQuit?
                    logger.debug(f"Unable to process {ops_service} {element}:\n{e}")
                finally:
                    if not uber_progress.finished:
                        uber_progress.update(namespace_task, advance=1)
                        uber_progress.update(uber_task, advance=1)

        for service in pending_work:
            if pending_work[service]:
                visually_process(
                    description=f"Processing {service}",
                    support_segment=pending_work[service],
                    ops_service=service,
                )

    write_zip(file_path=bundle_path, bundle=bundle)
    return {"bundlePath": bundle_path}


def write_zip(bundle: dict, file_path: str):
    with ZipFile(file=file_path, mode="w", compression=ZIP_DEFLATED) as myzip:
        todo: List[dict] = []
        for ops_service in bundle:
            for element in bundle[ops_service]:
                if isinstance(bundle[ops_service][element], list):
                    todo.extend(bundle[ops_service][element])
                else:
                    todo.append(bundle[ops_service][element])

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
