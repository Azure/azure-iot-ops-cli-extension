# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from itertools import groupby
from typing import Any, Dict, List, Optional, Tuple

from azext_edge.edge.providers.base import get_namespaced_pods_by_prefix

from .base import (
    CheckManager,
    add_display_and_eval,
    check_post_deployment,
    decorate_pod_phase,
    generate_target_resource_name,
    process_properties,
    resources_grouped_by_namespace,
)

from rich.padding import Padding
from kubernetes.client.models import V1Pod

from ...common import CheckTaskStatus

from .common import (
    AIO_LNM_PREFIX,
    ASSET_DATAPOINT_PROPERTIES,
    ASSET_PROPERTIES,
    CORE_SERVICE_RUNTIME_RESOURCE,
    LNM_ALLOWLIST_PROPERTIES,
    LNM_EXCLUDED_SUBRESOURCE,
    LNM_IMAGE_PROPERTIES,
    LNM_POD_CONDITION_TEXT_MAP,
    LNM_REST_PROPERTIES,
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    DEVICEREGISTRY_API_V1,
    DeviceRegistryResourceKinds,
)

from ..support.lnm import LNM_APP_LABELS, LNM_LABEL_PREFIX


def check_deviceregistry_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None
) -> None:
    evaluate_funcs = {
        DeviceRegistryResourceKinds.ASSET: evaluate_assets,
    }

    check_post_deployment(
        api_info=DEVICEREGISTRY_API_V1,
        check_name="enumerateDeviceRegistryApi",
        check_desc="Enumerate DeviceRegistry API resources",
        result=result,
        resource_kinds_enum=DeviceRegistryResourceKinds,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
    )


# def evaluate_core_service_runtime(
#     as_list: bool = False,
#     detail_level: int = ResourceOutputDetailLevel.summary.value,
# ) -> Dict[str, Any]:
#     check_manager = CheckManager(check_name="evalCoreServiceRuntime", check_desc="Evaluate LNM core service")

#     lnm_operator_label = f"app in ({','.join(LNM_APP_LABELS)})"
#     _process_lnm_pods(
#         check_manager=check_manager,
#         description="LNM runtime resources",
#         target=CORE_SERVICE_RUNTIME_RESOURCE,
#         prefix=AIO_LNM_PREFIX,
#         label_selector=lnm_operator_label,
#         padding=6,
#         detail_level=detail_level,
#     )

#     return check_manager.as_dict(as_list)


def evaluate_assets(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssets", check_desc="Evaluate Device Registry instances")

    lnm_namespace_conditions = ["spec.assetEndpointProfileUri", "spec.allowList", "spec.image"]

    all_assets: dict = DEVICEREGISTRY_API_V1.get_resources(DeviceRegistryResourceKinds.ASSET).get("items", [])
    target_assets = generate_target_resource_name(api_info=DEVICEREGISTRY_API_V1, resource_kind=DeviceRegistryResourceKinds.ASSET.value)

    if not all_assets:
        fetch_assets_warning_text = "Unable to fetch assets in any namespaces."
        check_manager.add_target(target_name=target_assets)
        check_manager.add_display(target_name=target_assets, display=Padding(fetch_assets_warning_text, (0, 0, 0, 8)))
        check_manager.add_target_eval(
            target_name=target_assets,
            status=CheckTaskStatus.skipped.value,
            value={"assets": None}
        )
        return check_manager.as_dict(as_list)

    for (namespace, assets) in resources_grouped_by_namespace(all_assets):
        check_manager.add_target(target_name=target_assets, namespace=namespace, conditions=lnm_namespace_conditions)
        check_manager.add_display(
            target_name=target_assets,
            namespace=namespace,
            display=Padding(
                f"Device Registry assets in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        assets: List[dict] = list(assets)

        for asset in assets:
            asset_name = asset["metadata"]["name"]

            asset_status_text = (
                f"- Asset {{[bright_blue]{asset_name}[/bright_blue]}} detected."
            )

            check_manager.add_display(
                target_name=target_assets,
                namespace=namespace,
                display=Padding(asset_status_text, (0, 0, 0, 10)),
            )

            asset_spec = asset["spec"]
            endpoint_profile_uri = asset_spec.get("assetEndpointProfileUri", "")

            endpoint_profile_uri_value = {"spec.assetEndpointProfileUri": endpoint_profile_uri}
            endpoint_profile_uri_status = CheckTaskStatus.success.value
            if endpoint_profile_uri:
                endpoint_profile_uri_text = (
                    f"Asset endpoint profile uri {{[bright_blue]{endpoint_profile_uri}[/bright_blue]}} property [green]detected[/green]."
                )
            else:
                endpoint_profile_uri_text = (
                    "Asset endpoint profile uri [red]not detected[/red]."
                )
                endpoint_profile_uri_status = CheckTaskStatus.error.value
            
            add_display_and_eval(
                check_manager=check_manager,
                target_name=target_assets,
                display_text=endpoint_profile_uri_text,
                eval_status=endpoint_profile_uri_status,
                eval_value=endpoint_profile_uri_value,
                resource_name=asset_name,
                namespace=namespace,
                padding=(0, 0, 0, 14)
            )

            # if detail_level > ResourceOutputDetailLevel.summary.value:
            #     # asset type
            #     asset_type = asset_spec.get("assetType", "")

            #     if asset_type:
            #         asset_type_text = (
            #             f"Asset Type: {asset_type}"
            #         )

            #         check_manager.add_display(
            #             target_name=target_assets,
            #             namespace=namespace,
            #             display=Padding(asset_type_text, (0, 0, 0, 12)),
            #         )
                
            #     if detail_level == ResourceOutputDetailLevel.verbose.value:
            #         # attibutes key-value pairs
            #         attributes = asset_spec.get("attributes", {})
            #         for attribute in attributes:
            #             attribute_name = attribute.get("name", "")
            #             attribute_value = attribute.get("value", "")
            #             attribute_text = (
            #                 f"Attribute {attribute_name} : {attribute_value}"
            #             )

            #             check_manager.add_display(
            #                 target_name=target_assets,
            #                 namespace=namespace,
            #                 display=Padding(attribute_text, (0, 0, 0, 12)),
            #             )
                    
            # data points
            data_points = asset_spec.get("dataPoints", [])
            check_manager.add_target_conditions(
                target_name=target_assets,
                namespace=namespace,
                conditions=["len(spec.dataPoints)"]
            )
            data_points_count = len(data_points)
            data_points_value = {"len(spec.dataPoints)": data_points_count}
            data_points_status = CheckTaskStatus.success.value

            if data_points_count > 1000:
                data_points_text = (
                    # expecting no more than 1000 data points per asset
                    f"Data points [red]exceeding 1000[/red]. Detected {data_points_count}."
                )
            else:
                data_points_text = (
                    f"[bright_blue]{data_points_count}[/bright_blue] data points detected."
                )
            
            add_display_and_eval(
                check_manager=check_manager,
                target_name=target_assets,
                display_text=data_points_text,
                eval_status=data_points_status,
                eval_value=data_points_value,
                resource_name=asset_name,
                namespace=namespace,
                padding=(0, 0, 0, 14)
            )

            for data_point in data_points:
                data_point_data_source = data_point.get("dataSource", "")

                check_manager.add_target_conditions(
                    target_name=target_assets,
                    namespace=namespace,
                    conditions=[f"spec.dataPoints.{data_point_data_source}.dataSource"]
                )
                data_point_data_source_value = {f"spec.dataPoints.{data_point_data_source}.dataSource": data_point_data_source}
                data_point_data_source_status = CheckTaskStatus.success.value
                if data_point_data_source:
                    data_point_data_source_text = (
                        f"- Data source: {{[bright_blue]{data_point_data_source}[/bright_blue]}} [green]detected[/green]."
                    )
                else:
                    data_point_data_source_text = (
                        "Data source [red]not detected[/red]."
                    )
                    data_point_data_source_status = CheckTaskStatus.error.value
                
                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_assets,
                    display_text=data_point_data_source_text,
                    eval_status=data_point_data_source_status,
                    eval_value=data_point_data_source_value,
                    resource_name=asset_name,
                    namespace=namespace,
                    padding=(0, 0, 0, 18)
                )

                if detail_level > ResourceOutputDetailLevel.summary.value:
                    process_properties(
                        check_manager=check_manager,
                        detail_level=detail_level,
                        target_name=target_assets,
                        prop_value=data_point,
                        properties=ASSET_DATAPOINT_PROPERTIES,
                        namespace=namespace,
                        padding=(0, 0, 0, 20)
                    )

            if detail_level > ResourceOutputDetailLevel.summary.value:
                process_properties(
                    check_manager=check_manager,
                    detail_level=detail_level,
                    target_name=target_assets,
                    prop_value=asset_spec,
                    properties=ASSET_PROPERTIES,
                    namespace=namespace,
                    padding=(0, 0, 0, 14)
                )
            
            # status
            status = asset_spec.get("status", "")
            if status:
                check_manager.add_target_conditions(
                    target_name=target_assets,
                    namespace=namespace,
                    conditions=["spec.status"]
                )

                status_value = {"spec.status": status}
                status_status = CheckTaskStatus.success.value

                errors = status.get("errors", [])
                if errors:
                    for error in errors:
                        error_code = error.get("code", "")
                        message = error.get("message", "")
                        error_text = (
                            f"- Asset status error code: [red]{error_code}[/red]. Message: {message}"
                        )
                        
                        check_manager.add_display(
                            target_name=target_assets,
                            namespace=namespace,
                            display=Padding(error_text, (0, 0, 0, 14)),
                        )
                    status_status = CheckTaskStatus.error.value
                else:
                    status_text = (
                        "- Asset status [green]OK[/green]."
                    )
                
                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_assets,
                    display_text=status_text,
                    eval_status=status_status,
                    eval_value=status_value,
                    resource_name=asset_name,
                    namespace=namespace,
                    padding=(0, 0, 0, 12)
                )

    return check_manager.as_dict(as_list)


def _process_lnm_pods(
    check_manager: CheckManager,
    description: str,
    target: str,
    prefix: str,
    padding: int,
    label_selector: Optional[str] = None,
    conditions: Optional[List[str]] = None,
    namespace: Optional[str] = None,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    def _get_lnm_pods_namespace(pod: V1Pod) -> str:
        return pod.metadata.namespace

    pods = get_namespaced_pods_by_prefix(prefix=prefix, namespace=namespace, label_selector=label_selector)

    pods.sort(key=_get_lnm_pods_namespace)
    for (namespace, pods) in groupby(pods, _get_lnm_pods_namespace):
        check_manager.add_target(target_name=target, namespace=namespace, conditions=conditions)
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"{description} in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, padding)
            )
        )

        for pod in pods:
            _evaluate_lnm_pod_health(
                check_manager=check_manager,
                target=target,
                pod=pod,
                display_padding=padding + 4,
                namespace=namespace,
                detail_level=detail_level,
            )

    return pods


def _evaluate_lnm_pod_health(
    check_manager: CheckManager,
    target: str,
    pod: V1Pod,
    display_padding: int,
    namespace: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:

    def _decorate_pod_condition(condition: bool) -> Tuple[str, str]:
        if condition:
            return f"[green]{condition}[/green]", CheckTaskStatus.success.value
        return f"[red]{condition}[/red]", CheckTaskStatus.error.value

    target_service_pod = f"pod/{pod.metadata.name}"

    pod_conditions = [
        f"{target_service_pod}.status.phase",
        f"{target_service_pod}.status.conditions.ready",
        f"{target_service_pod}.status.conditions.initialized",
        f"{target_service_pod}.status.conditions.containersready",
        f"{target_service_pod}.status.conditions.podscheduled",
    ]

    if check_manager.targets.get(target, {}).get(namespace, {}).get("conditions", None):
        check_manager.add_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)
    else:
        check_manager.set_target_conditions(target_name=target, namespace=namespace, conditions=pod_conditions)

    if not pod:
        add_display_and_eval(
            check_manager=check_manager,
            target_name=target,
            display_text=f"{target_service_pod}* [yellow]not detected[/yellow].",
            eval_status=CheckTaskStatus.warning.value,
            eval_value=None,
            resource_name=target_service_pod,
            namespace=namespace,
            padding=(0, 0, 0, display_padding)
        )
    else:
        pod_dict = pod.to_dict()
        pod_name = pod_dict["metadata"]["name"]
        pod_phase = pod_dict.get("status", {}).get("phase")
        pod_conditions = pod_dict.get("status", {}).get("conditions", {})
        pod_phase_deco, status = decorate_pod_phase(pod_phase)

        check_manager.add_target_eval(
            target_name=target,
            namespace=namespace,
            status=status,
            resource_name=target_service_pod,
            value={"name": pod_name, "status.phase": pod_phase},
        )

        for text in [
            f"\nPod {{[bright_blue]{pod_name}[/bright_blue]}}",
            f"- Phase: {pod_phase_deco}",
            "- Conditions:"
        ]:
            padding = 2 if "\nPod" not in text else 0
            padding += display_padding
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(text, (0, 0, 0, padding)),
            )

        for condition in pod_conditions:
            type = condition.get("type")
            condition_type = LNM_POD_CONDITION_TEXT_MAP[type]
            condition_status = True if condition.get("status") == "True" else False
            pod_condition_deco, status = _decorate_pod_condition(condition=condition_status)

            add_display_and_eval(
                check_manager=check_manager,
                target_name=target,
                display_text=f"{condition_type}: {pod_condition_deco}",
                eval_status=status,
                eval_value={"name": pod_name, f"status.conditions.{type.lower()}": condition_status},
                resource_name=target_service_pod,
                namespace=namespace,
                padding=(0, 0, 0, display_padding + 8)
            )

            if detail_level > ResourceOutputDetailLevel.summary.value:
                condition_reason = condition.get("message")
                condition_reason_text = f"{condition_reason}" if condition_reason else ""

                if condition_reason_text:
                    # remove the [ and ] to prevent console not printing the text
                    condition_reason_text = condition_reason_text.replace("[", "\\[")
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"[red]Reason: {condition_reason_text}[/red]",
                            (0, 0, 0, display_padding + 8),
                        ),
                    )
