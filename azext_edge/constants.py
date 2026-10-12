# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
"""This module defines constants for use across the CLI extension package"""

import os

VERSION = "2.11.0a2"
EXTENSION_NAME = "azure-iot-ops"
EXTENSION_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_AGENT = "IotOperationsCliExtension/{}".format(VERSION)
AIO_RELEASE = "2610"
PREVIEW_AGREEMENT_URL = "https://azure.microsoft.com/en-us/support/legal/preview-supplemental-terms/"
PREVIEW_NOTICE = (
    "Creating an Azure IoT Operations preview instance is subject to the Supplemental Terms of Use "
    "for Microsoft Azure Previews at the following URL."
)
