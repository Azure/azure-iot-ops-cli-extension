# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# PRIVATE DISTRIBUTION FOR NDA CUSTOMERS ONLY
# --------------------------------------------------------------------------------------------
"""This module defines constants for use across the CLI extension package"""

import os

VERSION = "0.0.1a6"
EXTENSION_NAME = "azure-edge"
EXTENSION_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_AGENT = "EdgePlatformCliExtension/{}".format(VERSION)
