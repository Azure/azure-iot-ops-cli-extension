# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from ....common import ListableEnum


class DestinationRetain(ListableEnum):
    """Retain flag for MQTT destinations."""
    never = "Never"
    keep = "Keep"


class DestinationQos(ListableEnum):
    """Quality of Service for MQTT destinations."""
    qos0 = "Qos0"
    qos1 = "Qos1"


class ActionType(Enum):
    """Type of action for management group actions."""
    call = "Call"
    read = "Read"
    write = "Write"
