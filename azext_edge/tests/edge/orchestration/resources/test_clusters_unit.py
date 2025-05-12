# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

from .conftest import BASE_URL
from .conftest import ZEROED_SUBSCRIPTION


def get_cluster_url(
    cluster_rg: str, cluster_name: str, cluster_sub_id: Optional[str] = None, just_id: bool = False
) -> str:
    if not cluster_sub_id:
        cluster_sub_id = ZEROED_SUBSCRIPTION
    # client uses lowercase resourcegroups
    cluster_id = (
        f"/subscriptions/{cluster_sub_id}/resourcegroups/{cluster_rg}"
        f"/providers/Microsoft.Kubernetes/connectedClusters/{cluster_name}"
    )
    if just_id:
        return cluster_id

    return f"{BASE_URL}{cluster_id}?api-version=2024-07-15-preview"


def get_federated_creds_url(
    uami_rg_name: str, uami_name: str, uami_sub_id: Optional[str] = None, fc_name: Optional[str] = None
) -> str:
    fc_name = f"/{fc_name}" if fc_name else ""
    if not uami_sub_id:
        uami_sub_id = ZEROED_SUBSCRIPTION
    return (
        f"{BASE_URL}/subscriptions/{uami_sub_id}/resourceGroups/{uami_rg_name}"
        f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/{uami_name}"
        f"/federatedIdentityCredentials{fc_name}?api-version=2023-01-31"
    )
