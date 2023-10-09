# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


from argparse import Namespace
from azure.cli.core.azclierror import InvalidArgumentValueError


def validate_namespace(namespace: Namespace):
    if hasattr(namespace, "namespace") and namespace.namespace:
        import re

        # TODO - this is technically less restrictive than the official RFC 1123 DNS Label spec (first and last character must be alphanumeric)
        if not re.fullmatch("[a-z0-9-]{1,63}", namespace.namespace):
            raise InvalidArgumentValueError(
                "Invalid namespace specifier: Limited to 63 total characters, only lowercase alphanumeric characters and '-' allowed."
            )
