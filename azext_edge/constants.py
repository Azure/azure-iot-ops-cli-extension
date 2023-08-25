# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------
"""This module defines constants for use across the CLI extension package"""

import os

VERSION = "0.0.3a3.dev1"
EXTENSION_NAME = "azure-edge"
EXTENSION_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_AGENT = "EdgePlatformCliExtension/{}".format(VERSION)
