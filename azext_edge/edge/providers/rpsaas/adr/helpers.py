# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from knack.log import get_logger
from typing import Dict, Optional
from azure.cli.core.azclierror import (
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
    InvalidArgumentValueError,
    FileOperationError
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


def get_default_dataset(asset: dict, dataset_name: str, create_if_none: bool = False):
    """
    Temporary helper function to get a dataset from an asset.

    If the dataset is not found but it has the name 'default' and create_if_none is True,
    it will create a new dataset with that name that is added to the asset's datasets.

    Will raise errors if the dataset is not found and create_if_none is False, or
    if the dataset name is not 'default' and create_if_none is True.
    """
    # ensure datasets will get populated if not there
    asset["properties"]["datasets"] = asset["properties"].get("datasets", [])
    datasets = asset["properties"]["datasets"]
    matched_datasets = [dset for dset in datasets if dset["name"] == dataset_name]
    # Temporary convert empty names to default
    if not matched_datasets and dataset_name == "default":
        matched_datasets = [dset for dset in datasets if dset["name"] == ""]
    # create if add or import (and no datasets yet)
    if not matched_datasets and create_if_none:
        if dataset_name != "default":
            raise InvalidArgumentValueError("Currently only one dataset with the name default is supported.")
        matched_datasets = [{}]
        datasets.extend(matched_datasets)
    elif not matched_datasets:
        raise InvalidArgumentValueError(f"Dataset {dataset_name} not found in asset {asset['name']}.")
    # note: right now we can have datasets with the same name but this will not be allowed later
    # part of the temporary convert
    matched_datasets[0]["name"] = dataset_name
    return matched_datasets[0]


def process_additional_configuration(
    additional_configuration: Optional[str] = None,
    config_type: str = "additional",
    **_
) -> Optional[str]:
    """
    Checks that the custom configuration is a valid JSON and returns the stringified JSON.
    If it is a file, it will read the content.
    """
    from ....util import read_file_content
    inline_json = False

    if not additional_configuration:
        return

    try:
        logger.debug(f"Processing {config_type} configuration.")
        additional_configuration = read_file_content(additional_configuration)
        if not additional_configuration:
            raise InvalidArgumentValueError("Given file is empty.")
    except FileOperationError:
        inline_json = True
        logger.debug(f"Given {config_type} configuration is not a file.")

    # make sure it is an actual json
    try:
        json.loads(additional_configuration)
        return additional_configuration
    except json.JSONDecodeError as e:
        error_msg = f"{config_type.capitalize()} configuration is not a valid JSON. "
        if inline_json:
            error_msg += "For examples of valid JSON formating, please see https://aka.ms/inline-json-examples "
        raise InvalidArgumentValueError(
            f"{error_msg}\n{e.msg}"
        )


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
    elif not auth_mode and not auth_props:
        auth_props["method"] = ADRAuthModes.anonymous.value
    elif any([auth_mode, certificate_reference, username_reference, password_reference]):
        raise MutuallyExclusiveArgumentError(GENERAL_AUTH_REF_MISMATCH_ERROR)

    return auth_props


def ensure_schema_structure(schema: dict, input_data: dict):
    """
    Quick and dirty alternative for using jsonschema (to avoid conflicts in other extensions).

    This partial implementation focuses on checks (in the current adr schemas) not covered by azure
    core parameter checks: minimum and maximum checks for integers. This handles nested objects and
    oneOf schemas.

    Not covered in this:
    - required properties checks
    - type checks
    - enum checks
    - array checks (cause the only schema with an array only has objects with string types)
    """
    def _recursive_check(schema: dict, input_data: dict) -> list:
        invalid_items = []

        # extract schemas from oneOf
        schemas = schema.get("oneOf", [schema])

        for sub_schema in schemas:
            schema_properties = sub_schema.get("properties", {})
            for key, value in input_data.items():
                if value is None:
                    # assume this is to clear the value
                    continue

                if key in schema_properties and ("type" in schema_properties[key]):
                    schema_value = schema_properties[key]
                    expected_type = schema_value["type"]

                    # go deeper if the expected type is an object
                    if expected_type == "object":
                        invalid_items.extend(_recursive_check(schema_value, value))

                    # lazy way of getting first item for now - assume that the second item is a null type
                    if isinstance(expected_type, list):
                        expected_type = expected_type[0]

                    # minimum and maximum checks for integers
                    if expected_type in ["integer", "number"]:
                        if (
                            "minimum" in schema_value
                            and "maximum" in schema_value
                            and not schema_value["minimum"] <= value <= schema_value["maximum"]
                        ):
                            invalid_items.append(
                                f"Invalid value for {key}: the value must be between {schema_value['minimum']} and "
                                f"{schema_value['maximum']} inclusive, instead got {value}"
                            )
                        elif "minimum" in schema_value and (value < schema_value["minimum"]):
                            invalid_items.append(
                                f"Invalid value for {key}: the value must be at least {schema_value['minimum']}, "
                                f"instead got {value}"
                            )
                        elif "maximum" in schema_value and (value > schema_value["maximum"]):
                            invalid_items.append(
                                f"Invalid value for {key}: the value must be at most {schema_value['maximum']}, "
                                f"instead got {value}"
                            )
            # maybe add popping keys that are not there?
        return invalid_items

    invalid_items = _recursive_check(schema, input_data)
    if invalid_items:
        error_msg = ', \n'.join(set(invalid_items))
        raise InvalidArgumentValueError(f"Invalid input data: {error_msg}")
