# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
"""This module defines constants for use across the CLI extension package"""

import os

VERSION = "0.6.0a3"
EXTENSION_NAME = "azure-iot-ops"
EXTENSION_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_AGENT = "IotOperationsCliExtension/{}".format(VERSION)
