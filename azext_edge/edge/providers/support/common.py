# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Callable, TypedDict


# resource label formats
COMPONENT_LABEL_FORMAT = "app.kubernetes.io/component in ({label})"
NAME_LABEL_FORMAT = "app.kubernetes.io/name in ({label})"
RESOURCE_NAME_FORMAT = "metadata.name={name}"


class ClusterResourceConfig(TypedDict):
    """Configuration for support bundle custom resources."""
    api_call: Callable[[Any, str], Any]
    api_client: Callable[[], Any]
    list_type: type
    filename: str
