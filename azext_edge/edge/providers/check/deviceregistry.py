# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List

from .base import (
    CheckManager,
    add_display_and_eval,
    check_post_deployment,
    generate_target_resource_name,
    get_resources_by_name,
    process_list_resource,
    process_resource_properties,
    get_resources_grouped_by_namespace,
)

from rich.padding import Padding

from ...common import CheckTaskStatus

from .common import (
    ASSET_DATAPOINT_PROPERTIES,
    ASSET_EVENT_PROPERTIES,
    ASSET_PROPERTIES,
    MAX_ASSET_DATAPOINTS,
    MAX_ASSET_EVENTS,
    PADDING_SIZE,
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    DEVICEREGISTRY_API_V1,
    DeviceRegistryResourceKinds,
)


def check_deviceregistry_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> None:
    evaluate_funcs = {
        DeviceRegistryResourceKinds.ASSET: evaluate_assets,
        DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE: evaluate_asset_endpoint_profiles,
    }

    check_post_deployment(
        api_info=DEVICEREGISTRY_API_V1,
        check_name="enumerateDeviceRegistryApi",
        check_desc="Enumerate Device Registry API resources",
        result=result,
        resource_name=resource_name,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
    )


def evaluate_assets(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssets", check_desc="Evaluate Device Registry instances")

    asset_namespace_conditions = ["spec.assetEndpointProfileUri"]

    target_assets = generate_target_resource_name(api_info=DEVICEREGISTRY_API_V1, resource_kind=DeviceRegistryResourceKinds.ASSET.value)

    all_assets = get_resources_by_name(
        api_info=DEVICEREGISTRY_API_V1,
        kind=DeviceRegistryResourceKinds.ASSET,
        resource_name=resource_name
    )

    if not all_assets:
        fetch_assets_warning_text = "Unable to fetch assets in any namespaces."
        check_manager.add_target(target_name=target_assets)
        check_manager.add_display(target_name=target_assets, display=Padding(fetch_assets_warning_text, (0, 0, 0, 8)))
        check_manager.add_target_eval(
            target_name=target_assets,
            status=CheckTaskStatus.skipped.value,
            value=fetch_assets_warning_text
        )
        return check_manager.as_dict(as_list)

    for (namespace, assets) in get_resources_grouped_by_namespace(all_assets):
        check_manager.add_target(target_name=target_assets, namespace=namespace, conditions=asset_namespace_conditions)
        check_manager.add_display(
            target_name=target_assets,
            namespace=namespace,
            display=Padding(
                f"Device Registry assets in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        assets: List[dict] = list(assets)

        added_datapoint_conditions = False
        added_event_conditions = False
        added_status_conditions = False
        for asset in assets:
            padding = 10
            asset_name = asset["metadata"]["name"]

            asset_status_text = (
                f"- Asset {{[bright_blue]{asset_name}[/bright_blue]}} detected."
            )

            check_manager.add_display(
                target_name=target_assets,
                namespace=namespace,
                display=Padding(asset_status_text, (0, 0, 0, padding)),
            )

            asset_spec = asset["spec"]
            endpoint_profile_uri = asset_spec.get("assetEndpointProfileUri", "")
            spec_padding = padding + PADDING_SIZE

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
                padding=(0, 0, 0, spec_padding)
            )

            # data points
            data_points = asset_spec.get("dataPoints", [])

            if data_points:
                if not added_datapoint_conditions:
                    check_manager.add_target_conditions(
                        target_name=target_assets,
                        namespace=namespace,
                        conditions=[
                            "len(spec.dataPoints)",
                            "spec.dataPoints.dataSource"
                        ]
                    )
                    added_datapoint_conditions = True

                data_points_count = len(data_points)
                data_points_value = {"len(spec.dataPoints)": data_points_count}
                data_points_status = CheckTaskStatus.success.value

                if data_points_count > MAX_ASSET_DATAPOINTS:
                    data_points_text = (
                        f"Data points [red]exceeding {MAX_ASSET_DATAPOINTS}[/red]. Detected {data_points_count}."
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
                    padding=(0, 0, 0, spec_padding)
                )

                for index, data_point in enumerate(data_points):
                    data_point_data_source = data_point.get("dataSource", "")
                    datapoint_padding = spec_padding + PADDING_SIZE
                    data_point_data_source_value = {f"spec.dataPoints.[{index}].dataSource": data_point_data_source}
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
                        padding=(0, 0, 0, datapoint_padding)
                    )

                    if detail_level > ResourceOutputDetailLevel.summary.value:
                        process_resource_properties(
                            check_manager=check_manager,
                            detail_level=detail_level,
                            target_name=target_assets,
                            prop_value=data_point,
                            properties=ASSET_DATAPOINT_PROPERTIES,
                            namespace=namespace,
                            padding=(0, 0, 0, datapoint_padding + PADDING_SIZE)
                        )

            if detail_level > ResourceOutputDetailLevel.summary.value:
                process_resource_properties(
                    check_manager=check_manager,
                    detail_level=detail_level,
                    target_name=target_assets,
                    prop_value=asset_spec,
                    properties=ASSET_PROPERTIES,
                    namespace=namespace,
                    padding=(0, 0, 0, spec_padding)
                )

            # events
            events = asset_spec.get("events", [])
            if events:
                if not added_event_conditions:
                    check_manager.add_target_conditions(
                        target_name=target_assets,
                        namespace=namespace,
                        conditions=[
                            "len(spec.events)",
                            "spec.events.eventNotifier"
                        ]
                    )
                    added_event_conditions = True

                events_count = len(events)
                events_count_value = {"len(spec.events)": events_count}
                events_count_status = CheckTaskStatus.success.value

                if events_count > MAX_ASSET_EVENTS:
                    events_count_text = (
                        f"Events [red]exceeding {MAX_ASSET_EVENTS}[/red]. Detected {events_count}."
                    )
                    events_count_status = CheckTaskStatus.error.value
                else:
                    events_count_text = (
                        f"[bright_blue]{events_count}[/bright_blue] events detected."
                    )

                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_assets,
                    display_text=events_count_text,
                    eval_status=events_count_status,
                    eval_value=events_count_value,
                    resource_name=asset_name,
                    namespace=namespace,
                    padding=(0, 0, 0, spec_padding)
                )

                for index, event in enumerate(events):
                    event_notifier = event.get("eventNotifier", "")
                    event_padding = spec_padding + PADDING_SIZE
                    event_notifier_value = {f"spec.events.[{index}].eventNotifier": event_notifier}
                    event_notifier_status = CheckTaskStatus.success.value
                    if event_notifier:
                        event_notifier_text = (
                            f"- Event notifier: {{[bright_blue]{event_notifier}[/bright_blue]}} [green]detected[/green]."
                        )
                    else:
                        event_notifier_text = (
                            "Event notifier [red]not detected[/red]."
                        )
                        event_notifier_status = CheckTaskStatus.error.value

                    add_display_and_eval(
                        check_manager=check_manager,
                        target_name=target_assets,
                        display_text=event_notifier_text,
                        eval_status=event_notifier_status,
                        eval_value=event_notifier_value,
                        resource_name=asset_name,
                        namespace=namespace,
                        padding=(0, 0, 0, event_padding)
                    )

                    if detail_level > ResourceOutputDetailLevel.summary.value:
                        process_resource_properties(
                            check_manager=check_manager,
                            detail_level=detail_level,
                            target_name=target_assets,
                            prop_value=event,
                            properties=ASSET_EVENT_PROPERTIES,
                            namespace=namespace,
                            padding=(0, 0, 0, event_padding + PADDING_SIZE)
                        )

            # status
            status = asset_spec.get("status", "")
            if status:
                _process_asset_status(
                    check_manager=check_manager,
                    added_status_conditions=added_status_conditions,
                    target_assets=target_assets,
                    asset_name=asset_name,
                    status=status,
                    padding=spec_padding,
                    namespace=namespace
                )

    return check_manager.as_dict(as_list)


def evaluate_asset_endpoint_profiles(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssetEndpointProfiles", check_desc="Evaluate Asset Endpoint Profiles")

    endpoint_namespace_conditions = ["spec.uuid"]

    all_asset_endpoint_profiles = get_resources_by_name(
        api_info=DEVICEREGISTRY_API_V1,
        kind=DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE,
        resource_name=resource_name
    )
    target_asset_endpoint_profiles = generate_target_resource_name(api_info=DEVICEREGISTRY_API_V1, resource_kind=DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE.value)

    if not all_asset_endpoint_profiles:
        fetch_asset_endpoint_profiles_warning_text = "Unable to fetch asset endpoint profiles in any namespaces."
        check_manager.add_target(target_name=target_asset_endpoint_profiles)
        check_manager.add_display(target_name=target_asset_endpoint_profiles, display=Padding(fetch_asset_endpoint_profiles_warning_text, (0, 0, 0, 8)))
        check_manager.add_target_eval(
            target_name=target_asset_endpoint_profiles,
            status=CheckTaskStatus.skipped.value,
            value=fetch_asset_endpoint_profiles_warning_text
        )
        return check_manager.as_dict(as_list)

    for (namespace, asset_endpoint_profiles) in get_resources_grouped_by_namespace(all_asset_endpoint_profiles):
        check_manager.add_target(target_name=target_asset_endpoint_profiles, namespace=namespace, conditions=endpoint_namespace_conditions)
        check_manager.add_display(
            target_name=target_asset_endpoint_profiles,
            namespace=namespace,
            display=Padding(
                f"Asset Endpoint Profiles in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        asset_endpoint_profiles: List[dict] = list(asset_endpoint_profiles)

        added_transport_authentication_conditions = False
        added_user_authentication_conditions = False
        for asset_endpoint_profile in asset_endpoint_profiles:
            asset_endpoint_profile_name = asset_endpoint_profile["metadata"]["name"]
            padding = 10

            asset_endpoint_profile_status_text = (
                f"- Profile {{[bright_blue]{asset_endpoint_profile_name}[/bright_blue]}} detected."
            )

            check_manager.add_display(
                target_name=target_asset_endpoint_profiles,
                namespace=namespace,
                display=Padding(asset_endpoint_profile_status_text, (0, 0, 0, padding)),
            )

            spec_padding = padding + PADDING_SIZE
            asset_endpoint_profile_spec = asset_endpoint_profile["spec"]
            endpoint_profile_uuid = asset_endpoint_profile_spec.get("uuid", "")

            endpoint_profile_uuid_value = {"spec.uuid": endpoint_profile_uuid}
            endpoint_profile_uuid_status = CheckTaskStatus.success.value

            if endpoint_profile_uuid:
                endpoint_profile_uuid_text = (
                    f"Uuid: {{[bright_blue]{endpoint_profile_uuid}[/bright_blue]}} [green]detected[/green]."
                )
            else:
                endpoint_profile_uuid_text = (
                    "Uuid [red]not detected[/red]."
                )
                endpoint_profile_uuid_status = CheckTaskStatus.error.value

            add_display_and_eval(
                check_manager=check_manager,
                target_name=target_asset_endpoint_profiles,
                display_text=endpoint_profile_uuid_text,
                eval_status=endpoint_profile_uuid_status,
                eval_value=endpoint_profile_uuid_value,
                resource_name=asset_endpoint_profile_name,
                namespace=namespace,
                padding=(0, 0, 0, spec_padding)
            )

            # transportAuthentication
            transport_authentication = asset_endpoint_profile_spec.get("transportAuthentication", {})
            if transport_authentication:
                if not added_transport_authentication_conditions:
                    check_manager.add_target_conditions(
                        target_name=target_asset_endpoint_profiles,
                        namespace=namespace,
                        conditions=[
                            "spec.transportAuthentication.ownCertificates"
                        ]
                    )
                    added_transport_authentication_conditions = True

                check_manager.add_display(
                    target_name=target_asset_endpoint_profiles,
                    namespace=namespace,
                    display=Padding(
                        "Transport authentication:",
                        (0, 0, 0, spec_padding)
                    )
                )
                transport_authentication_own_certificates = transport_authentication.get("ownCertificates", None)
                transport_authentication_own_certificates_value = {"spec.transportAuthentication.ownCertificates": transport_authentication_own_certificates}
                transport_authentication_own_certificates_status = CheckTaskStatus.success.value
                transport_authentication_padding = spec_padding + PADDING_SIZE

                if transport_authentication_own_certificates is None:
                    transport_authentication_own_certificates_text = (
                        "Own certificates [red]not detected[/red]."
                    )
                    transport_authentication_own_certificates_status = CheckTaskStatus.error.value
                else:
                    transport_authentication_own_certificates_text = (
                        f"Own certificates: {len(transport_authentication_own_certificates)} detected."
                    )

                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_asset_endpoint_profiles,
                    display_text=transport_authentication_own_certificates_text,
                    eval_status=transport_authentication_own_certificates_status,
                    eval_value=transport_authentication_own_certificates_value,
                    resource_name=asset_endpoint_profile_name,
                    namespace=namespace,
                    padding=(0, 0, 0, transport_authentication_padding)
                )

                if detail_level > ResourceOutputDetailLevel.detail.value and transport_authentication_own_certificates:
                    process_list_resource(
                        check_manager=check_manager,
                        target_name=target_asset_endpoint_profiles,
                        resource=transport_authentication_own_certificates,
                        namespace=namespace,
                        padding=transport_authentication_padding + PADDING_SIZE
                    )

            # userAuthentication
            user_authentication = asset_endpoint_profile_spec.get("userAuthentication", {})
            if user_authentication:
                if not added_user_authentication_conditions:
                    check_manager.add_target_conditions(
                        target_name=target_asset_endpoint_profiles,
                        namespace=namespace,
                        conditions=[
                            "spec.userAuthentication.mode",
                            "spec.userAuthentication.x509Credentials.certificateReference",
                            "spec.userAuthentication.usernamePasswordCredentials.usernameReference",
                            "spec.userAuthentication.usernamePasswordCredentials.passwordReference"
                        ]
                    )
                    added_user_authentication_conditions = True

                check_manager.add_display(
                    target_name=target_asset_endpoint_profiles,
                    namespace=namespace,
                    display=Padding(
                        "User authentication:",
                        (0, 0, 0, spec_padding)
                    )
                )

                # check required mode
                user_authentication_mode = user_authentication.get("mode", "")
                user_authentication_mode_value = {"spec.userAuthentication.mode": user_authentication_mode}
                user_authentication_mode_status = CheckTaskStatus.success.value
                user_authentication_padding = spec_padding + PADDING_SIZE

                if user_authentication_mode:
                    user_authentication_mode_text = (
                        f"User authentication mode: {{[bright_blue]{user_authentication_mode}[/bright_blue]}} [green]detected[/green]."
                    )
                else:
                    user_authentication_mode_text = (
                        "User authentication mode [red]not detected[/red]."
                    )
                    user_authentication_mode_status = CheckTaskStatus.error.value

                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_asset_endpoint_profiles,
                    display_text=user_authentication_mode_text,
                    eval_status=user_authentication_mode_status,
                    eval_value=user_authentication_mode_value,
                    resource_name=asset_endpoint_profile_name,
                    namespace=namespace,
                    padding=(0, 0, 0, user_authentication_padding)
                )

                if user_authentication_mode == "Certificate":
                    # check x509Credentials
                    user_authentication_x509_credentials = user_authentication.get("x509Credentials", {})

                    certificate_reference = user_authentication_x509_credentials.get("certificateReference", "")
                    user_authentication_x509_credentials_value = {"spec.userAuthentication.x509Credentials.certificateReference": certificate_reference}
                    user_authentication_x509_credentials_status = CheckTaskStatus.success.value
                    if certificate_reference:
                        user_authentication_x509_credentials_text = (
                            f"Certificate reference: {{[bright_blue]{certificate_reference}[/bright_blue]}} [green]detected[/green]."
                        )
                    else:
                        user_authentication_x509_credentials_text = (
                            "Certificate reference [red]not detected[/red]."
                        )
                        user_authentication_x509_credentials_status = CheckTaskStatus.error.value

                    add_display_and_eval(
                        check_manager=check_manager,
                        target_name=target_asset_endpoint_profiles,
                        display_text=user_authentication_x509_credentials_text,
                        eval_status=user_authentication_x509_credentials_status,
                        eval_value=user_authentication_x509_credentials_value,
                        resource_name=asset_endpoint_profile_name,
                        namespace=namespace,
                        padding=(0, 0, 0, user_authentication_padding + PADDING_SIZE)
                    )

                elif user_authentication_mode == "UsernamePassword":
                    # check usernamePasswordCredentials
                    user_authentication_username_password_credentials = user_authentication.get("usernamePasswordCredentials", {})
                    username_reference = user_authentication_username_password_credentials.get("usernameReference", "")
                    password_reference = user_authentication_username_password_credentials.get("passwordReference", "")
                    user_authentication_username_password_credentials_value = {
                        "spec.userAuthentication.usernamePasswordCredentials.usernameReference": username_reference,
                        "spec.userAuthentication.usernamePasswordCredentials.passwordReference": password_reference
                    }
                    user_authentication_username_password_credentials_status = CheckTaskStatus.success.value
                    if username_reference and password_reference:
                        user_authentication_username_password_credentials_text = (
                            f"Username reference: {{[bright_blue]{username_reference}[/bright_blue]}} [green]detected[/green].\n"
                            f"Password reference: {{[bright_blue]{password_reference}[/bright_blue]}} [green]detected[/green]."
                        )
                    else:
                        user_authentication_username_password_credentials_text = (
                            "Username reference or password reference [red]not detected[/red]."
                        )
                        user_authentication_username_password_credentials_status = CheckTaskStatus.error.value

                    add_display_and_eval(
                        check_manager=check_manager,
                        target_name=target_asset_endpoint_profiles,
                        display_text=user_authentication_username_password_credentials_text,
                        eval_status=user_authentication_username_password_credentials_status,
                        eval_value=user_authentication_username_password_credentials_value,
                        resource_name=asset_endpoint_profile_name,
                        namespace=namespace,
                        padding=(0, 0, 0, user_authentication_padding + PADDING_SIZE)
                    )

            if detail_level > ResourceOutputDetailLevel.summary.value:
                process_resource_properties(
                    check_manager=check_manager,
                    detail_level=detail_level,
                    target_name=target_asset_endpoint_profiles,
                    prop_value=asset_endpoint_profile_spec,
                    properties=[
                        ("additionalConfiguration", "Additional configuration", True),
                        ("targetAddress", "Target address", False),
                    ],
                    namespace=namespace,
                    padding=(0, 0, 0, spec_padding)
                )

    return check_manager.as_dict(as_list)


def _process_asset_status(
    check_manager: CheckManager,
    added_status_conditions: bool,
    target_assets: str,
    asset_name: str,
    status: dict,
    padding: int,
    namespace: str,
):
    if not added_status_conditions:
        check_manager.add_target_conditions(
            target_name=target_assets,
            namespace=namespace,
            conditions=["spec.status"]
        )
        added_status_conditions = True

    status_value = {"spec.status": str(status)}
    status_status = CheckTaskStatus.success.value

    errors = status.get("errors", [])
    if errors:
        status_text = (
            "Asset status [red]error[/red]."
        )
        for error in errors:
            error_code = error.get("code", "")
            message = error.get("message", "")
            error_text = (
                f"- Asset status error code: [red]{error_code}[/red]. Message: {message}"
            )

            check_manager.add_display(
                target_name=target_assets,
                namespace=namespace,
                display=Padding(error_text, (0, 0, 0, padding + PADDING_SIZE)),
            )
        status_status = CheckTaskStatus.error.value
    else:
        status_text = (
            "Asset status [green]OK[/green]."
        )

    add_display_and_eval(
        check_manager=check_manager,
        target_name=target_assets,
        display_text=status_text,
        eval_status=status_status,
        eval_value=status_value,
        resource_name=asset_name,
        namespace=namespace,
        padding=(0, 0, 0, padding)
    )
