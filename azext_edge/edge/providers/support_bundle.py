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
    CERTMANAGER_API_V1,
    CLUSTER_CONFIG_API_V1,
    CONTAINERSTORAGE_API_V1,
    MQTT_BROKER_API_V1,
    OPENSERVICEMESH_CONFIG_API_V1,
    OPENSERVICEMESH_POLICY_API_V1,
    DEVICEREGISTRY_API_V1,
    DATAFLOW_API_V1,
    META_API_V1,
    ARCCONTAINERSTORAGE_API_V1,
    SECRETSYNC_API_V1,
    SECRETSTORE_API_V1,
    TRUSTMANAGER_API_V1,
    AZUREMONITOR_API_V1,
    EdgeApiManager,
)

logger = get_logger(__name__)

console = Console()

COMPAT_CERTMANAGER_APIS = EdgeApiManager(resource_apis=[CERTMANAGER_API_V1, TRUSTMANAGER_API_V1])
COMPAT_CLUSTER_CONFIG_APIS = EdgeApiManager(resource_apis=[CLUSTER_CONFIG_API_V1])
COMPAT_MQTT_BROKER_APIS = EdgeApiManager(resource_apis=[MQTT_BROKER_API_V1])
COMPAT_OSM_APIS = EdgeApiManager(resource_apis=[OPENSERVICEMESH_CONFIG_API_V1, OPENSERVICEMESH_POLICY_API_V1])
COMPAT_DEVICEREGISTRY_APIS = EdgeApiManager(resource_apis=[DEVICEREGISTRY_API_V1])
COMPAT_DATAFLOW_APIS = EdgeApiManager(resource_apis=[DATAFLOW_API_V1])
COMPAT_META_APIS = EdgeApiManager(resource_apis=[META_API_V1])
COMPAT_ARCCONTAINERSTORAGE_APIS = EdgeApiManager(resource_apis=[ARCCONTAINERSTORAGE_API_V1, CONTAINERSTORAGE_API_V1])
COMPAT_SECRETSTORE_APIS = EdgeApiManager(resource_apis=[SECRETSYNC_API_V1, SECRETSTORE_API_V1])
COMPAT_AZUREMONITOR_APIS = EdgeApiManager(resource_apis=[AZUREMONITOR_API_V1])


def build_bundle(
    bundle_path: str,
    log_age_seconds: Optional[int] = None,
    ops_services: Optional[List[str]] = None,
    include_mq_traces: Optional[bool] = None,
):
    from rich.live import Live
    from rich.progress import Progress
    from rich.table import Table

    from .support.billing import prepare_bundle as prepare_billing_bundle
    from .support.mq import prepare_bundle as prepare_mq_bundle
    from .support.openservicemesh import prepare_bundle as prepare_openservicemesh_bundle
    from .support.connectors import prepare_bundle as prepare_connector_bundle
    from .support.dataflow import prepare_bundle as prepare_dataflow_bundle
    from .support.deviceregistry import prepare_bundle as prepare_deviceregistry_bundle
    from .support.shared import prepare_bundle as prepare_shared_bundle
    from .support.akri import prepare_bundle as prepare_akri_bundle
    from .support.arcagents import prepare_bundle as prepare_arcagents_bundle
    from .support.meta import prepare_bundle as prepare_meta_bundle
    from .support.schemaregistry import prepare_bundle as prepare_schema_registry_bundle
    from .support.arccontainerstorage import prepare_bundle as prepare_arccontainerstorage_bundle
    from .support.secretstore import prepare_bundle as prepare_secretstore_bundle
    from .support.azuremonitor import prepare_bundle as prepare_azuremonitor_bundle
    from .support.certmanager import prepare_bundle as prepare_certmanager_bundle
    from .support.meso import prepare_bundle as prepare_meso_bundle

    def collect_default_works(
        pending_work: dict,
        log_age_seconds: Optional[int] = None,
    ):
        # arc agent resources
        pending_work["arcagents"] = prepare_arcagents_bundle(log_age_seconds)

        # Collect common resources if any AIO service is deployed with any service selected.
        pending_work["common"] = prepare_shared_bundle()

        # Collect meta resources if any AIO service is deployed with any service selected.
        deployed_meta_apis = COMPAT_META_APIS.get_deployed()
        pending_work["meta"] = prepare_meta_bundle(log_age_seconds, deployed_meta_apis)

    pending_work = {k: {} for k in OpsServiceType.list()}

    api_map = {
        OpsServiceType.mq.value: {"apis": COMPAT_MQTT_BROKER_APIS, "prepare_bundle": prepare_mq_bundle},
        OpsServiceType.billing.value: {
            "apis": COMPAT_CLUSTER_CONFIG_APIS,
            "prepare_bundle": prepare_billing_bundle,
        },
        OpsServiceType.openservicemesh.value: {
            "apis": COMPAT_OSM_APIS,
            "prepare_bundle": prepare_openservicemesh_bundle,
        },
        OpsServiceType.connectors.value: {
            "apis": None,
            "prepare_bundle": prepare_connector_bundle,
        },
        OpsServiceType.akri.value: {"apis": None, "prepare_bundle": prepare_akri_bundle},
        OpsServiceType.deviceregistry.value: {
            "apis": COMPAT_DEVICEREGISTRY_APIS,
            "prepare_bundle": prepare_deviceregistry_bundle,
        },
        OpsServiceType.dataflow.value: {
            "apis": COMPAT_DATAFLOW_APIS,
            "prepare_bundle": prepare_dataflow_bundle,
        },
        OpsServiceType.schemaregistry.value: {
            "apis": None,
            "prepare_bundle": prepare_schema_registry_bundle,
        },
        OpsServiceType.arccontainerstorage.value: {
            "apis": COMPAT_ARCCONTAINERSTORAGE_APIS,
            "prepare_bundle": prepare_arccontainerstorage_bundle,
        },
        OpsServiceType.secretstore.value: {
            "apis": COMPAT_SECRETSTORE_APIS,
            "prepare_bundle": prepare_secretstore_bundle,
        },
        OpsServiceType.azuremonitor.value: {
            "apis": COMPAT_AZUREMONITOR_APIS,
            "prepare_bundle": prepare_azuremonitor_bundle,
        },
        OpsServiceType.certmanager.value: {
            "apis": COMPAT_CERTMANAGER_APIS,
            "prepare_bundle": prepare_certmanager_bundle,
        },
        OpsServiceType.meso.value: {
            "apis": None,
            "prepare_bundle": prepare_meso_bundle,
        },
    }

    if not ops_services:
        parsed_ops_services = OpsServiceType.list()
    else:
        # remove duplicates
        parsed_ops_services = list(set(ops_services))

    for ops_service in parsed_ops_services:
        # assign key and value to service_moniker and api_info
        service_moniker = [k for k, _ in api_map.items() if k == ops_service][0]
        api_info = api_map.get(service_moniker)
        deployed_apis = api_info["apis"].get_deployed() if api_info["apis"] else None

        if not deployed_apis and service_moniker not in [
            OpsServiceType.schemaregistry.value,
            OpsServiceType.akri.value,
            OpsServiceType.connectors.value,
            OpsServiceType.meso.value,
        ]:
            expected_api_version = api_info["apis"].as_str()
            logger.warning(
                f"The following API(s) were not detected {expected_api_version}. "
                f"CR capture for {service_moniker} will be skipped. "
                "Still attempting capture of runtime resources..."
            )

        # still try fetching other resources even crds are not available due to api version mismatch
        bundle_method = api_info["prepare_bundle"]
        # Check if the function takes a second argument
        # TODO: Change to kwargs based pattern
        if service_moniker == OpsServiceType.deviceregistry.value:
            bundle = bundle_method(deployed_apis)
        elif service_moniker == OpsServiceType.mq.value:
            bundle = bundle_method(log_age_seconds, deployed_apis, include_mq_traces)
        elif service_moniker in [
            OpsServiceType.schemaregistry.value,
            OpsServiceType.akri.value,
            OpsServiceType.connectors.value,
            OpsServiceType.meso.value,
        ]:
            bundle = bundle_method(log_age_seconds)
        else:
            bundle = bundle_method(log_age_seconds, deployed_apis)

        pending_work[service_moniker].update(bundle)

    collect_default_works(pending_work, log_age_seconds)

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
