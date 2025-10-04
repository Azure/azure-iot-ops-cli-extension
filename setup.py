#!/usr/bin/env python
# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import re
import os.path
from io import open
from setuptools import setup


EXTENSION_REF_NAME = "azext_edge"

# Extraction inspired from 'requests'
with open(os.path.join(EXTENSION_REF_NAME, "constants.py"), "r", encoding="utf-8") as fd:
    constants_raw = fd.read()
    IOTOPS_TARGET = re.search(r'^IOTOPS_TARGET\s*=\s*[\'"]([^\'"]*)[\'"]', constants_raw, re.MULTILINE).group(1)

if not IOTOPS_TARGET:
    raise RuntimeError("Cannot find AIO release information.")


setup(
    project_urls={
        "Homepage": "https://github.com/azure/azure-iot-ops-cli-extension",
        "X-AIO-Target": f"aio://release/{IOTOPS_TARGET}",
    }
)
