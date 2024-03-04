# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from argparse import Namespace
from azure.cli.core.azclierror import InvalidArgumentValueError


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
