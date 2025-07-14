# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from ...common import ListableEnum


class DestinationQos(ListableEnum):
    """Quality of Service for MQTT destinations."""
    qos0 = "Qos0"
    qos1 = "Qos1"


class ActionType(Enum):
    """Type of action for management group actions."""
    call = "Call"
    read = "Read"
    write = "Write"


class FileType(ListableEnum):
    """
    Supported file types/extensions for bulk asset operations.
    """

    json = "json"
    csv = "csv"
    yaml = "yaml"


class ADRAuthModes(Enum):
    """
    Authentication modes for asset endpoints/devices
    """

    anonymous = "Anonymous"
    certificate = "Certificate"
    userpass = "UsernamePassword"


class AEPTypes(ListableEnum):
    """Asset Endpoint Profile (connector) Types"""

    opcua = "Microsoft.OpcUa"
    onvif = "Microsoft.Onvif"


class TopicRetain(ListableEnum):
    """Set the retain flag for messages published to an MQTT broker."""

    keep = "Keep"
    never = "Never"
