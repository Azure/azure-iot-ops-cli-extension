# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from typing import Dict, Optional
from azure.cli.core.azclierror import (
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)
from .user_strings import (
    AUTH_REF_MISMATCH_ERROR,
    GENERAL_AUTH_REF_MISMATCH_ERROR,
    MISSING_USERPASS_REF_ERROR,
    REMOVED_CERT_REF_MSG,
    REMOVED_USERPASS_REF_MSG,
)
from ...orchestration.resources import Instances
from ....common import ADRAuthModes

logger = get_logger(__name__)


def check_cluster_connectivity(cmd, resource: dict):
    """
    Uses the resource's extended location to get the cluster and checks connectivity.
    Use this for commands that require the cluster to be connected to succeed.

    resource: dict representing an object that has the extended location property.

    """
    connected_cluster = Instances(cmd=cmd).get_resource_map(resource).connected_cluster
    if not connected_cluster.connected:
        logger.warning(f"Cluster {connected_cluster.cluster_name} is not connected.")


def get_extended_location(
    cmd,
    instance_name: str,
    instance_resource_group: str,
    instance_subscription: Optional[str] = None
) -> Dict[str, str]:
    """
    Returns the extended location object with cluster location.

    Will also check for instance existance and whether the associated cluster is connected.

    instance_name: str representing the instance name
    instance_resource_group: str representing the instance resource group
    instance_subscription: str representing the instance subscription
        (if it is different from the current one)
    """
    instance_provider = Instances(cmd=cmd, subscription_id=instance_subscription)
    # instance should exist
    instance = instance_provider.show(
        name=instance_name, resource_group_name=instance_resource_group
    )
    resource_map = instance_provider.get_resource_map(instance=instance)
    connected_cluster = resource_map.connected_cluster
    if not connected_cluster.connected:
        logger.warning(f"Cluster {connected_cluster.cluster_name} is not connected.")

    return {
        "type": "CustomLocation",
        "name": instance["extendedLocation"]["name"],
        "cluster_location": connected_cluster.location
    }


def process_authentication(
    auth_mode: Optional[str] = None,
    auth_props: Optional[Dict[str, str]] = None,
    certificate_reference: Optional[str] = None,
    password_reference: Optional[str] = None,
    username_reference: Optional[str] = None
) -> Dict[str, str]:
    """
    Create an authentication object to be used by namespace devices and AEPs.

    This will follow one of following format:
    {
        "method": "Anonymous"
    }

    or

    {
        "method": "UsernamePassword",
        "usernamePasswordCredentials": {
            "passwordSecretName": "str",
            "usernameSecretName": "str"
        }
    }

    or

    {
        "method": "Certificate",
        "x509Credentials": {
            "certificateSecretName":
                "str"
        }
    }
    """
    if not auth_props:
        auth_props = {}

    # add checking for ensuring auth mode is set with proper params
    if certificate_reference and (username_reference or password_reference):
        raise MutuallyExclusiveArgumentError(AUTH_REF_MISMATCH_ERROR)

    if certificate_reference and auth_mode in [None, ADRAuthModes.certificate.value]:
        auth_props["method"] = ADRAuthModes.certificate.value
        auth_props["x509Credentials"] = {"certificateSecretName": certificate_reference}
        if auth_props.pop("usernamePasswordCredentials", None):
            logger.warning(REMOVED_USERPASS_REF_MSG)
    elif (username_reference or password_reference) and auth_mode in [None, ADRAuthModes.userpass.value]:
        auth_props["method"] = ADRAuthModes.userpass.value
        user_creds = auth_props.get("usernamePasswordCredentials", {})
        user_creds["usernameSecretName"] = username_reference
        user_creds["passwordSecretName"] = password_reference
        if not all([user_creds["usernameSecretName"], user_creds["passwordSecretName"]]):
            raise RequiredArgumentMissingError(MISSING_USERPASS_REF_ERROR)
        auth_props["usernamePasswordCredentials"] = user_creds
        if auth_props.pop("x509Credentials", None):
            logger.warning(REMOVED_CERT_REF_MSG)
    elif auth_mode == ADRAuthModes.anonymous.value and not any(
        [certificate_reference, username_reference, password_reference]
    ):
        auth_props["method"] = ADRAuthModes.anonymous.value
        if auth_props.pop("x509Credentials", None):
            logger.warning(REMOVED_CERT_REF_MSG)
        if auth_props.pop("usernamePasswordCredentials", None):
            logger.warning(REMOVED_USERPASS_REF_MSG)
    elif any([auth_mode, certificate_reference, username_reference, password_reference]):
        raise MutuallyExclusiveArgumentError(GENERAL_AUTH_REF_MISMATCH_ERROR)

    return auth_props
