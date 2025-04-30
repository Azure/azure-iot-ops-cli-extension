# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

from .conftest import (
    get_base_endpoint,
    get_mock_resource,
)

SECRETSYNC_RP = "Microsoft.SecretSyncController"
SECRETSYNC_RP_API_VERSION = "2024-08-21-preview"


def get_secretsync_endpoint(resource_group_name: Optional[str] = None, spc_name: Optional[str] = None) -> str:
    resource_path = "/secretSyncs"
    if spc_name:
        resource_path += f"/{spc_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=SECRETSYNC_RP,
        api_version=SECRETSYNC_RP_API_VERSION,
    )


def get_mock_secretsync_record(
    name: str, resource_group_name: str, location: Optional[str] = None, cl_name: Optional[str] = None
) -> dict:
    optional_kwargs = {}
    if cl_name:
        optional_kwargs["custom_location_name"] = cl_name
    record = get_mock_resource(
        name=name,
        resource_provider=SECRETSYNC_RP,
        resource_path=f"/secretSyncs/{name}",
        location=location,
        properties={
            "provisioningState": "Succeeded",
            "kubernetesSecretType": "Opaque",
            "objectSecretMapping": [
                {"sourcePath": "secret1", "targetKey": "password"},
                {"sourcePath": "secret2", "targetKey": "username"},
            ],
            "secretProviderClassName": "spc-ops-068b143",
            "serviceAccountName": "aio-ssc-sa",
            "status": {},
        },
        resource_group_name=resource_group_name,
        qualified_type=f"{SECRETSYNC_RP}/secretSyncs",
        **optional_kwargs,
    )
    return record
