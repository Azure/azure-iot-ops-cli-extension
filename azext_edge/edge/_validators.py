# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from argparse import Namespace
from azure.cli.core.azclierror import InvalidArgumentValueError


def validate_secret_sync_name(value: str) -> str:
    import re

    label = r"[a-z0-9](?:[-a-z0-9]*[a-z0-9])?"
    if len(value) > 253 or not re.fullmatch(rf"{label}(?:\.{label})*", value):
        raise InvalidArgumentValueError(
            "--secret-sync-name must be a Kubernetes Secret name: at most 253 characters, "
            "with dot-separated lowercase alphanumeric or hyphenated labels "
            "that start and end with an alphanumeric character."
        )
    return value


def validate_connector_metadata_ref(namespace: Namespace):
    from .providers.orchestration.resources.connectors import validate_metadata_reference

    validate_metadata_reference(namespace.connector_metadata_ref)


def validate_namespace(namespace: Namespace):
    if hasattr(namespace, "namespace") and namespace.namespace:
        import re

        # TODO - this is less restrictive than the official RFC 1123 DNS Label spec,
        # first and last character must be alphanumeric
        if not re.fullmatch("[a-z0-9-]{1,63}", namespace.namespace):
            raise InvalidArgumentValueError(
                f"Invalid namespace specifier '{namespace.namespace}': Limited to 63 total characters, "
                "only lowercase alphanumeric characters and '-' allowed."
            )


def validate_resource_name(namespace: Namespace):
    if hasattr(namespace, "resource_name") and namespace.resource_name:
        import re

        # validate resource_name that should only contain alphanumeric characters, hyphens, ? and *
        if not re.fullmatch(r"[a-zA-Z0-9\-?*]+", namespace.resource_name):
            raise InvalidArgumentValueError(
                f"Invalid resource name '{namespace.resource_name}'. "
                "Only alphanumeric characters, hyphens, ? and * are allowed."
            )
