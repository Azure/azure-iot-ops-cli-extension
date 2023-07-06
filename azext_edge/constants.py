# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
"""This module defines constants for use across the CLI extension package"""

import os

VERSION = "0.0.1a4"
EXTENSION_NAME = "azure-edge"
EXTENSION_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_AGENT = "EdgePlatformCliExtension/{}".format(VERSION)
