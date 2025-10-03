# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

from ...conftest import (
    INSTANCES_API_VERSION,
    RESOURCE_PROVIDER,
    get_base_endpoint,
    get_mock_resource,
)


def get_connector_template_endpoint(
    instance_name: str, resource_group_name: Optional[str] = None, template_name: Optional[str] = None
) -> str:
    resource_path = f"/instances/{instance_name}/akriConnectorTemplates"
    if template_name:
        resource_path += f"/{template_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=RESOURCE_PROVIDER,
        api_version=INSTANCES_API_VERSION,
    )


def get_mock_connector_template_record(
    name: str,
    instance_name: str,
    resource_group_name: str,
    location: Optional[str] = None,
    cl_name: Optional[str] = None,
) -> dict:
    optional_kwargs = {}
    if cl_name:
        optional_kwargs["custom_location_name"] = cl_name
    record = get_mock_resource(
        name=name,
        resource_provider=RESOURCE_PROVIDER,
        resource_path=f"/instances/{instance_name}/akriConnectorTemplates/{name}",
        location=location,
        properties={
            "aioMetadata": {},
            "diagnostics": {"logs": {"level": "info"}},
            "deviceInboundEndpointTypes": [
                {
                    "configurationSchemaRefs": {
                        "additionalConfigSchemaRef": "aio-sr://target4/microsoft-onvif-7722a864:1",
                        "defaultEventsConfigSchemaRef": "aio-sr://target4/microsoft-onvif-51b86567:1",
                        "defaultProcessControlConfigSchemaRef": "aio-sr://target4/microsoft-onvif-52de1fd3:1",
                    },
                    "endpointType": "Microsoft.Onvif",
                }
            ],
            "runtimeConfiguration": {
                "runtimeConfigurationType": "ManagedConfiguration",
                "managedConfigurationSettings": {
                    "managedConfigurationType": "ImageConfiguration",
                    "imageConfigurationSettings": {
                        "imageName": "aio-connectors/onvif-connector",
                        "imagePullPolicy": "Never",
                        "replicas": 2,
                        "registrySettings": {
                            "registrySettingsType": "ContainerRegistry",
                            "containerRegistrySettings": {
                                "registry": "mcr.microsoft.com",
                                "imagePullSecrets": [{"secretRef": "abcde"}],
                            },
                        },
                        "tagDigestSettings": {"tagDigestType": "Tag", "tag": "1.2.12"},
                    },
                    "allocation": {"policy": "Bucketized", "bucketSize": 1},
                    "additionalConfiguration": {"key1": "value1"},
                },
            },
        },
        resource_group_name=resource_group_name,
        qualified_type=f"{RESOURCE_PROVIDER}/instances/akriConnectorTemplates",
        is_proxy_resource=True,
        **optional_kwargs,
    )
    return record
