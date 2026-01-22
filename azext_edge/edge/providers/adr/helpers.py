# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from knack.log import get_logger
from typing import Dict, Optional, Union
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
from ..orchestration.resources import Instances
from .common import ADRAuthModes
from ...util.id_tools import parse_resource_id

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
    instance_subscription: Optional[str] = None,
) -> Dict[str, Optional[Union[str, Dict[str, str]]]]:
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

    # for the new adr
    namespace = instance["properties"].get("adrNamespaceRef", {}).get("resourceId")
    if namespace:
        namespace = parse_resource_id(rid=namespace)

    return {
        "type": "CustomLocation",
        "name": instance["extendedLocation"]["name"],
        "cluster_location": connected_cluster.location,
        "namespace": namespace
    }


def get_namespace_for_instance(
    cmd,
    instance_name: str,
    instance_resource_group: str,
    instance_subscription: Optional[str] = None,
) -> Dict[str, str]:
    """
    Returns the namespace resource for the given instance.
    """
    instance_provider = Instances(cmd=cmd, subscription_id=instance_subscription)
    # instance should exist
    instance = instance_provider.show(
        name=instance_name, resource_group_name=instance_resource_group
    )
    namespace = instance["properties"].get("adrNamespaceRef", {}).get("resourceId")
    if not namespace:
        raise InvalidArgumentValueError(
            f"Instance {instance_name} does not have an Device Registry namespace associated with it. "
            "Please update your instance to use new Device Registry features."
        )

    return parse_resource_id(rid=namespace)


def get_instance_query(
    query: str,
    instance_name: Optional[str] = None,
    instance_resource_group: Optional[str] = None,
    project_away_custom_location: bool = True
) -> str:
    """
    Appends and returns query with instance filtering.
    """
    if any([instance_name, instance_resource_group]):
        instance_query = "Resources | where type =~ 'microsoft.iotoperations/instances' "
        if instance_name:
            instance_query += f"| where name =~ \"{instance_name}\" "
        if instance_resource_group:
            instance_query += f"| where resourceGroup =~ \"{instance_resource_group}\" "

        # make sure the custom location is extended
        if "| extend customLocation = tostring(extendedLocation.name)" not in query:
            query += " | extend customLocation = tostring(extendedLocation.name)"

        # fetch the custom location + join on innerunique. Then remove the extra customLocation1 generated
        query = (
            f"{instance_query}| extend customLocation = tostring(extendedLocation.name) "
            "| project customLocation | join kind=innerunique "
            f"({query}) on customLocation "
            "| project-away customLocation1"
        )
        if project_away_custom_location:
            query += ", customLocation"
    return query


def get_query(param_mapping: Dict[str, str], params: Dict[str, Union[str, bool]]) -> str:
    """
    Returns a query string based on the provided parameters and their mappings.

    Disabled is treated as a boolean and should not be in the param mapping.
    """
    query = []
    if "disabled" in params and params["disabled"] is not None:
        query.append(f"| where properties.enabled == {not params.pop('disabled')}")
    for param, value in params.items():
        # TODO: later, add in null support (ex: no os set)
        if value is not None:
            query.append(f"| where {param_mapping.get(param)} =~ \"{value}\"")

    return " ".join(query)


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
    from ...util import read_file_content
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


def _setup_certificate_authentication(
    auth_props: Dict[str, str],
    certificate_reference: str,
    key_reference: Optional[str] = None,
    intermediate_certificate_reference: Optional[str] = None,
) -> None:
    """Setup certificate-based authentication."""
    auth_props["method"] = ADRAuthModes.certificate.value

    x509_credentials = {"certificateSecretName": certificate_reference}

    if key_reference:
        x509_credentials["keySecretName"] = key_reference

    if intermediate_certificate_reference:
        x509_credentials["intermediateCertificatesSecretName"] = intermediate_certificate_reference

    auth_props["x509Credentials"] = x509_credentials
    if auth_props.pop("usernamePasswordCredentials", None):
        logger.warning(REMOVED_USERPASS_REF_MSG)

    return auth_props


def _setup_username_password_authentication(
    auth_props: Dict[str, str],
    username_reference: str,
    password_reference: str,
) -> None:
    """Setup username/password-based authentication."""
    auth_props["method"] = ADRAuthModes.userpass.value
    user_creds = auth_props.get("usernamePasswordCredentials", {})
    user_creds["usernameSecretName"] = username_reference
    user_creds["passwordSecretName"] = password_reference

    if not all([user_creds["usernameSecretName"], user_creds["passwordSecretName"]]):
        raise RequiredArgumentMissingError(MISSING_USERPASS_REF_ERROR)

    auth_props["usernamePasswordCredentials"] = user_creds
    if auth_props.pop("x509Credentials", None):
        logger.warning(REMOVED_CERT_REF_MSG)


def _setup_anonymous_authentication(auth_props: Dict[str, str]) -> None:
    """Setup anonymous authentication."""
    auth_props["method"] = ADRAuthModes.anonymous.value
    if auth_props.pop("x509Credentials", None):
        logger.warning(REMOVED_CERT_REF_MSG)
    if auth_props.pop("usernamePasswordCredentials", None):
        logger.warning(REMOVED_USERPASS_REF_MSG)


def process_authentication(
    auth_mode: Optional[str] = None,
    auth_props: Optional[Dict[str, str]] = None,
    certificate_reference: Optional[str] = None,
    key_reference: Optional[str] = None,
    intermediate_certificate_reference: Optional[str] = None,
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
            "certificateSecretName": "str",
            "keySecretName": "str",  # optional
            "intermediateCertificatesSecretName": "str"  # optional
        }
    }
    """
    if not auth_props:
        auth_props = {}

    # Validate that optional certificate fields are only used with required certificate_reference
    if (key_reference or intermediate_certificate_reference) and not certificate_reference:
        raise RequiredArgumentMissingError(
            "Certificate reference (--cert-ref) is required when using --key-ref or --intermediate-cert-ref."
        )

    # add checking for ensuring auth mode is set with proper params
    if certificate_reference and (username_reference or password_reference):
        raise MutuallyExclusiveArgumentError(AUTH_REF_MISMATCH_ERROR)

    if certificate_reference and auth_mode in [None, ADRAuthModes.certificate.value]:
        _setup_certificate_authentication(
            auth_props,
            certificate_reference,
            key_reference,
            intermediate_certificate_reference
        )
    elif (username_reference or password_reference) and auth_mode in [None, ADRAuthModes.userpass.value]:
        _setup_username_password_authentication(
            auth_props, username_reference, password_reference
        )
    elif auth_mode == ADRAuthModes.anonymous.value and not any(
        [certificate_reference, username_reference, password_reference]
    ):
        _setup_anonymous_authentication(auth_props)
    elif not auth_mode and not auth_props:
        auth_props["method"] = ADRAuthModes.anonymous.value
    elif any([auth_mode, certificate_reference, username_reference, password_reference]):
        raise MutuallyExclusiveArgumentError(GENERAL_AUTH_REF_MISMATCH_ERROR)

    return auth_props


def ensure_schema_structure(schema: dict, input_data: dict, name: Optional[str] = None):
    """
    Validates the input data against the provided schema using jsonschema.
    """
    import jsonschema

    validator = jsonschema.validators.validator_for(schema)(schema)
    errors = sorted(validator.iter_errors(input_data), key=lambda e: str(list(e.path)))

    if errors:
        final_messages = []
        for error in errors:
            path = ".".join([str(p) for p in error.path])
            if error.validator in ["oneOf", "anyOf"] and error.context:
                # Try to find the most relevant error from the context
                # We prefer errors that are not about structural mismatch (like additionalProperties)
                # if there are other errors available.
                context_errors = error.context
                # Filter for errors that indicate a value mismatch rather than a structure mismatch
                value_errors = [
                    e for e in context_errors
                    if e.validator not in ["additionalProperties", "required", "type", "const", "enum"]
                ]

                best = jsonschema.exceptions.best_match(value_errors or context_errors)
                msg = best.message
            else:
                msg = error.message

            if path:
                final_messages.append(f"Property '{path}' is invalid: {msg}")
            else:
                final_messages.append(f"Invalid configuration: {msg}")

        error_msg = "\n".join(final_messages)
        prefix = f"The following {name} values are invalid:\n" if name else "Invalid input data:\n"
        raise InvalidArgumentValueError(f"{prefix}{error_msg}")
