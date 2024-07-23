# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List

from knack.log import get_logger
from rich.padding import Padding

from azext_edge.edge.providers.check.base.pod import process_pod_status
from azext_edge.edge.providers.check.base.resource import filter_resources_by_name
from azext_edge.edge.providers.edge_api.dataflow import DATAFLOW_API_V1B1, DataflowResourceKinds

from ...common import CheckTaskStatus
from ..base import get_namespaced_pods_by_prefix
from ..support.dataflow import DATAFLOW_NAME_LABEL, DATAFLOW_OPERATOR_PREFIX
from .base import CheckManager, check_post_deployment, get_resources_by_name, get_resources_grouped_by_namespace
from .common import (
    COLOR_STR_FORMAT,
    PADDING_SIZE,
    CoreServiceResourceKinds,
    ResourceOutputDetailLevel,
)

logger = get_logger(__name__)


def check_dataflows_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> None:
    evaluate_funcs = {
        CoreServiceResourceKinds.RUNTIME_RESOURCE: evaluate_core_service_runtime,
        DataflowResourceKinds.DATAFLOWPROFILE: evaluate_dataflow_profiles,
        DataflowResourceKinds.DATAFLOW: evaluate_dataflows,
        DataflowResourceKinds.DATAFLOWENDPOINT: evaluate_dataflow_endpoints,
    }

    check_post_deployment(
        api_info=DATAFLOW_API_V1B1,
        check_name="enumerateDataflowApi",
        check_desc="Enumerate Dataflow API resources",
        result=result,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
        resource_name=resource_name,
    )


def evaluate_core_service_runtime(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflowRuntime",
        check_desc="Evaluate Dataflow Runtime Resources",
    )

    padding = 6
    operators = get_namespaced_pods_by_prefix(
        prefix="",
        namespace="",
        label_selector=DATAFLOW_NAME_LABEL,
    )
    if resource_name:
        operators = filter_resources_by_name(
            resources=operators,
            resource_name=resource_name,
        )

    if not operators:
        check_manager.add_target(target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value)
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            display=Padding("Unable to fetch pods.", (0, 0, 0, padding + 2)),
        )

    for namespace, pods in get_resources_grouped_by_namespace(operators):
        check_manager.add_target(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
        )
        check_manager.add_display(
            target_name=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            namespace=namespace,
            display=Padding(
                f"Dataflow runtime resources in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, padding),
            ),
        )

        process_pod_status(
            check_manager=check_manager,
            target_service_pod=f"pod/{DATAFLOW_OPERATOR_PREFIX}",
            target=CoreServiceResourceKinds.RUNTIME_RESOURCE.value,
            pods=pods,
            namespace=namespace,
            display_padding=padding + PADDING_SIZE,
            detail_level=detail_level,
        )

    return check_manager.as_dict(as_list)


def evaluate_dataflows(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflows",
        check_desc="Evaluate Dataflows",
    )
    all_dataflows = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOW,
        resource_name=resource_name,
    )
    target = "dataflows.connectivity.iotoperations.azure.com"
    padding = 8
    if not all_dataflows:
        no_dataflows_text = "No Dataflow resources detected in any namespace."
        check_manager.add_target(target_name=target)
        check_manager.add_target_eval(
            target_name=target,
            status=CheckTaskStatus.skipped.value,
            value={"dataflows": no_dataflows_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_dataflows_text, (0, 0, 0, padding)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, dataflows in get_resources_grouped_by_namespace(all_dataflows):
        check_manager.add_target(target_name=target, namespace=namespace)
        padding = 8
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Dataflows in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, padding)
            )
        )
        for dataflow in list(dataflows):
            padding = 8
            spec = dataflow.get("spec", {})
            dataflow_name = dataflow.get("metadata", {}).get("name")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"\n- Dataflow {{{COLOR_STR_FORMAT.format(color='bright_blue', value=dataflow_name)}}} {COLOR_STR_FORMAT.format(color='green', value='detected')}", (0, 0, 0, padding)),
            )
            padding += 4
            mode = spec.get("mode")
            profile_ref = spec.get("profileRef")
            for label, val in [
                ("Dataflow Profile", f"{{{COLOR_STR_FORMAT.format(color='bright_blue', value=profile_ref)}}}"),
                ("Mode", mode),
            ]:
                # TODO - validate profile ref
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: {val}", (0, 0, 0, padding)),
                )
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=CheckTaskStatus.success.value,
                resource_name=dataflow_name,
                resource_kind=DataflowResourceKinds.DATAFLOW.value,
            )
    return check_manager.as_dict(as_list=as_list)


def evaluate_dataflow_endpoints(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflowEndpoints",
        check_desc="Evaluate Dataflow Endpoints",
    )
    all_endpoints = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWENDPOINT,
        resource_name=resource_name,
    )
    target = "dataflowendpoints.connectivity.iotoperations.azure.com"
    padding = 8
    if not all_endpoints:
        no_endpoints_text = "No Dataflow Endpoints detected in any namespace."
        check_manager.add_target(target_name=target)
        check_manager.add_target_eval(
            target_name=target,
            status=CheckTaskStatus.skipped.value,
            value={"endpoints": no_endpoints_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_endpoints_text, (0, 0, 0, padding)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, endpoints in get_resources_grouped_by_namespace(all_endpoints):
        padding = 8
        check_manager.add_target(target_name=target, namespace=namespace)
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Dataflow Endpoints in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, padding)
            )
        )
        for endpoint in list(endpoints):
            padding = 8
            spec = endpoint.get("spec", {})
            endpoint_name = endpoint.get("metadata", {}).get("name")
            endpoint_type = spec.get("endpointType")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"\n- Endpoint {{{COLOR_STR_FORMAT.format(color='bright_blue', value=endpoint_name)}}} {COLOR_STR_FORMAT.format(color='green', value='detected')}", (0, 0, 0, padding)),
            )
            # TODO - figure out status
            padding += 4
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"Type: {COLOR_STR_FORMAT.format(color='bright_blue', value=endpoint_type)}", (0, 0, 0, padding)),
            )

            # endpoint auth
            auth = spec.get("authentication", {})
            auth_method = auth.get("method")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"Authentication Method: {auth_method}", (0, 0, 0, padding)),
            )

        check_manager.add_target_eval(
            target_name=target,
            namespace=namespace,
            status=CheckTaskStatus.success.value,
            resource_name=endpoint_name,
            resource_kind=DataflowResourceKinds.DATAFLOWENDPOINT.value,
        )
    return check_manager.as_dict(as_list=as_list)


def evaluate_dataflow_profiles(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
):
    check_manager = CheckManager(
        check_name="evalDataflowProfiles",
        check_desc="Evaluate Dataflow Profiles",
    )
    all_profiles = get_resources_by_name(
        api_info=DATAFLOW_API_V1B1,
        kind=DataflowResourceKinds.DATAFLOWPROFILE,
        resource_name=resource_name,
    )
    target = "dataflowprofiles.connectivity.iotoperations.azure.com"
    padding = 8
    if not all_profiles:
        no_profiles_text = "No Dataflow Profiles detected in any namespace."
        check_manager.add_target(target_name=target)
        check_manager.add_target_eval(
            target_name=target,
            status=CheckTaskStatus.skipped.value,
            value={"profiles": no_profiles_text}
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(no_profiles_text, (0, 0, 0, padding)),
        )
        return check_manager.as_dict(as_list=as_list)
    for namespace, profiles in get_resources_grouped_by_namespace(all_profiles):
        padding = 8
        check_manager.add_target(target_name=target, namespace=namespace)
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Dataflow Profiles in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, padding)
            )
        )
        for profile in list(profiles):
            padding = 8
            spec = profile.get("spec", {})
            profile_name = profile.get("metadata", {}).get("name")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"\n- Profile {{{COLOR_STR_FORMAT.format(color='bright_blue', value=profile_name)}}} {COLOR_STR_FORMAT.format(color='green', value='detected')}", (0, 0, 0, padding)),
            )

            # TODO - determine status
            check_manager.set_target_status(
                target_name=target,
                namespace=namespace,
                status=CheckTaskStatus.success.value,
            )
            check_manager.add_target_eval(
                target_name=target,
                namespace=namespace,
                status=CheckTaskStatus.success.value,
                resource_name=profile_name,
                resource_kind=DataflowResourceKinds.DATAFLOWPROFILE.value,
            )
    return check_manager.as_dict(as_list=as_list)
