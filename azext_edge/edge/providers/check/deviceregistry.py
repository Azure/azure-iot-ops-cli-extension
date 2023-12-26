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
    process_properties,
    resources_grouped_by_namespace,
)

from rich.padding import Padding

from ...common import CheckTaskStatus

from .common import (
    ASSET_DATAPOINT_PROPERTIES,
    ASSET_ENDPOINT_OWNCERTIFICATE_PROPERTIES,
    ASSET_EVENT_PROPERTIES,
    ASSET_PROPERTIES,
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
    resource_kinds: List[str] = None
) -> None:
    evaluate_funcs = {
        DeviceRegistryResourceKinds.ASSET: evaluate_assets,
        DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE: evaluate_asset_endpoint_profiles,
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


def evaluate_assets(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssets", check_desc="Evaluate Device Registry instances")

    asset_namespace_conditions = ["spec.assetEndpointProfileUri"]

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

            # data points
            data_points = asset_spec.get("dataPoints", [])

            if data_points:
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
                    index = data_points.index(data_point)

                    check_manager.add_target_conditions(
                        target_name=target_assets,
                        namespace=namespace,
                        conditions=[f"spec.dataPoints.[{index}].dataSource"]
                    )
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

            # events
            events = asset_spec.get("events", [])
            if events:
                check_manager.add_target_conditions(
                    target_name=target_assets,
                    namespace=namespace,
                    conditions=["len(spec.events)"]
                )
                events_count = len(events)
                events_count_value = {"len(spec.events)": events_count}
                events_count_status = CheckTaskStatus.success.value

                if events_count > 1000:
                    events_count_text = (
                        # expecting no more than 1000 events per asset
                        f"Events [red]exceeding 1000[/red]. Detected {events_count}."
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
                    padding=(0, 0, 0, 14)
                )

                for event in events:
                    event_notifier = event.get("eventNotifier", "")
                    index = events.index(event)

                    check_manager.add_target_conditions(
                        target_name=target_assets,
                        namespace=namespace,
                        conditions=[f"spec.events.[{index}].eventNotifier"]
                    )
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
                        padding=(0, 0, 0, 18)
                    )

                    if detail_level > ResourceOutputDetailLevel.summary.value:
                        process_properties(
                            check_manager=check_manager,
                            detail_level=detail_level,
                            target_name=target_assets,
                            prop_value=event,
                            properties=ASSET_EVENT_PROPERTIES,
                            namespace=namespace,
                            padding=(0, 0, 0, 20)
                        )

            # status
            status = asset_spec.get("status", "")
            if status:
                check_manager.add_target_conditions(
                    target_name=target_assets,
                    namespace=namespace,
                    conditions=["spec.status"]
                )

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
                            display=Padding(error_text, (0, 0, 0, 18)),
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
                    padding=(0, 0, 0, 14)
                )

    return check_manager.as_dict(as_list)


def evaluate_asset_endpoint_profiles(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalAssetEndpointProfiles", check_desc="Evaluate Asset Endpoint Profiles")

    lnm_namespace_conditions = ["spec.uuid"]

    all_asset_endpoint_profiles: dict = DEVICEREGISTRY_API_V1.get_resources(DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE).get("items", [])
    target_asset_endpoint_profiles = generate_target_resource_name(api_info=DEVICEREGISTRY_API_V1, resource_kind=DeviceRegistryResourceKinds.ASSETENDPOINTPROFILE.value)

    if not all_asset_endpoint_profiles:
        fetch_asset_endpoint_profiles_warning_text = "Unable to fetch asset endpoint profiles in any namespaces."
        check_manager.add_target(target_name=target_asset_endpoint_profiles)
        check_manager.add_display(target_name=target_asset_endpoint_profiles, display=Padding(fetch_asset_endpoint_profiles_warning_text, (0, 0, 0, 8)))
        check_manager.add_target_eval(
            target_name=target_asset_endpoint_profiles,
            status=CheckTaskStatus.skipped.value,
            value={"assetEndpointProfiles": None}
        )
        return check_manager.as_dict(as_list)

    for (namespace, asset_endpoint_profiles) in resources_grouped_by_namespace(all_asset_endpoint_profiles):
        check_manager.add_target(target_name=target_asset_endpoint_profiles, namespace=namespace, conditions=lnm_namespace_conditions)
        check_manager.add_display(
            target_name=target_asset_endpoint_profiles,
            namespace=namespace,
            display=Padding(
                f"Asset Endpoint Profiles in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        asset_endpoint_profiles: List[dict] = list(asset_endpoint_profiles)

        for asset_endpoint_profile in asset_endpoint_profiles:
            asset_endpoint_profile_name = asset_endpoint_profile["metadata"]["name"]

            asset_endpoint_profile_status_text = (
                f"- Asset endpoint profile {{[bright_blue]{asset_endpoint_profile_name}[/bright_blue]}} detected."
            )

            check_manager.add_display(
                target_name=target_asset_endpoint_profiles,
                namespace=namespace,
                display=Padding(asset_endpoint_profile_status_text, (0, 0, 0, 10)),
            )

            asset_endpoint_profile_spec = asset_endpoint_profile["spec"]
            endpoint_profile_uuid = asset_endpoint_profile_spec.get("uuid", "")

            endpoint_profile_uuid_value = {"spec.uuid": endpoint_profile_uuid}
            endpoint_profile_uuid_status = CheckTaskStatus.success.value

            if endpoint_profile_uuid:
                endpoint_profile_uuid_text = (
                    f"Endpoint profile uuid: {{[bright_blue]{endpoint_profile_uuid}[/bright_blue]}} [green]detected[/green]."
                )
            else:
                endpoint_profile_uuid_text = (
                    "Endpoint profile uuid [red]not detected[/red]."
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
                padding=(0, 0, 0, 14)
            )

            # transportAuthentication
            transport_authentication = asset_endpoint_profile_spec.get("transportAuthentication", {})
            if transport_authentication:
                check_manager.add_display(
                    target_name=target_asset_endpoint_profiles,
                    namespace=namespace,
                    display=Padding(
                        "Transport authentication:",
                        (0, 0, 0, 14)
                    )
                )
                transport_authentication_own_certificates = transport_authentication.get("ownCertificates", None)
                check_manager.add_target_conditions(
                    target_name=target_asset_endpoint_profiles,
                    namespace=namespace,
                    conditions=["spec.transportAuthentication.ownCertificates"]
                )

                transport_authentication_own_certificates_value = {"spec.transportAuthentication.ownCertificates": transport_authentication_own_certificates}
                transport_authentication_own_certificates_status = CheckTaskStatus.success.value

                if transport_authentication_own_certificates is None:
                    transport_authentication_own_certificates_text = (
                        "Own certificates [red]not detected[/red]."
                    )
                    transport_authentication_own_certificates_status = CheckTaskStatus.error.value
                else:
                    transport_authentication_own_certificates_text = (
                        f"Own certificates: {len(transport_authentication_own_certificates)} [green]detected[/green]."
                    )

                add_display_and_eval(
                    check_manager=check_manager,
                    target_name=target_asset_endpoint_profiles,
                    display_text=transport_authentication_own_certificates_text,
                    eval_status=transport_authentication_own_certificates_status,
                    eval_value=transport_authentication_own_certificates_value,
                    resource_name=asset_endpoint_profile_name,
                    namespace=namespace,
                    padding=(0, 0, 0, 18)
                )

                if detail_level > ResourceOutputDetailLevel.detail.value and transport_authentication_own_certificates:
                    for ownCertificate in transport_authentication_own_certificates:
                        index = transport_authentication_own_certificates.index(ownCertificate)
                        check_manager.add_display(
                            target_name=target_asset_endpoint_profiles,
                            namespace=namespace,
                            display=Padding(
                                f"- Own certificate {index}:",
                                (0, 0, 0, 22)
                            )
                        )
                        process_properties(
                            check_manager=check_manager,
                            detail_level=detail_level,
                            target_name=target_asset_endpoint_profiles,
                            prop_value=ownCertificate,
                            properties=ASSET_ENDPOINT_OWNCERTIFICATE_PROPERTIES,
                            namespace=namespace,
                            padding=(0, 0, 0, 26)
                        )

            # userAuthentication
            user_authentication = asset_endpoint_profile_spec.get("userAuthentication", {})
            if user_authentication:
                check_manager.add_display(
                    target_name=target_asset_endpoint_profiles,
                    namespace=namespace,
                    display=Padding(
                        "User authentication:",
                        (0, 0, 0, 14)
                    )
                )

                # check required mode
                user_authentication_mode = user_authentication.get("mode", "")
                check_manager.add_target_conditions(
                    target_name=target_asset_endpoint_profiles,
                    namespace=namespace,
                    conditions=["spec.userAuthentication.mode"]
                )

                user_authentication_mode_value = {"spec.userAuthentication.mode": user_authentication_mode}
                user_authentication_mode_status = CheckTaskStatus.success.value

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
                    padding=(0, 0, 0, 18)
                )

                if user_authentication_mode == "Certificate":
                    # check x509Credentials
                    user_authentication_x509_credentials = user_authentication.get("x509Credentials", {})
                    check_manager.add_target_conditions(
                        target_name=target_asset_endpoint_profiles,
                        namespace=namespace,
                        conditions=["spec.userAuthentication.x509Credentials.certificateReference"]
                    )

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
                        padding=(0, 0, 0, 22)
                    )

                elif user_authentication_mode == "UsernamePassword":
                    # check usernamePasswordCredentials
                    user_authentication_username_password_credentials = user_authentication.get("usernamePasswordCredentials", {})
                    check_manager.add_target_conditions(
                        target_name=target_asset_endpoint_profiles,
                        namespace=namespace,
                        conditions=["spec.userAuthentication.usernamePasswordCredentials.usernameReference", "spec.userAuthentication.usernamePasswordCredentials.passwordReference"]
                    )

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
                        padding=(0, 0, 0, 22)
                    )

            if detail_level > ResourceOutputDetailLevel.summary.value:
                process_properties(
                    check_manager=check_manager,
                    detail_level=detail_level,
                    target_name=target_asset_endpoint_profiles,
                    prop_value=asset_endpoint_profile_spec,
                    properties=[
                        ("additionalConfiguration", "Additional configuration", True),
                        ("targetAddress", "Target address", False),
                    ],
                    namespace=namespace,
                    padding=(0, 0, 0, 14)
                )

    return check_manager.as_dict(as_list)
