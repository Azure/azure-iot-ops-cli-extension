# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Callable, List, Optional, TypedDict

# resource label formats
COMPONENT_LABEL_FORMAT = "app.kubernetes.io/component in ({label})"
NAME_LABEL_FORMAT = "app.kubernetes.io/name in ({label})"
RESOURCE_NAME_FORMAT = "metadata.name={name}"


class ResourceSelectors(TypedDict, total=False):
    label_selectors: Optional[List[str]]
    field_selectors: Optional[List[str]]


class ClusterResourceConfig(TypedDict):
    """Configuration for support bundle cluster-wide resource aggregation."""

    api_call: Callable[[Optional[str], Optional[str]], Any]  # Function that takes (label_selector, field_selector)
    filename: str
