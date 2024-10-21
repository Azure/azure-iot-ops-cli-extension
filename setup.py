#!/usr/bin/env python
# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import re
import os.path
from io import open
from setuptools import setup, find_packages


EXTENSION_REF_NAME = "azext_edge"

# Version extraction inspired from 'requests'
with open(os.path.join(EXTENSION_REF_NAME, "constants.py"), "r", encoding="utf-8") as fd:
    constants_raw = fd.read()
    VERSION = re.search(r'^VERSION\s*=\s*[\'"]([^\'"]*)[\'"]', constants_raw, re.MULTILINE).group(1)
    PACKAGE_NAME = re.search(r'^EXTENSION_NAME\s*=\s*[\'"]([^\'"]*)[\'"]', constants_raw, re.MULTILINE).group(1)


if not VERSION:
    raise RuntimeError("Cannot find version information")

if not PACKAGE_NAME:
    raise RuntimeError("Cannot find package information")


DEPENDENCIES = [
    "packaging"
    "rich>=13.6,<14.0",
    "kubernetes>=27.2,<29.0",
    "azure-identity>=1.14.1,<1.18.0",
    "protobuf~=4.25.0",
    "opentelemetry-proto~=1.20.0",
    "packaging>=23.2",
]

CLASSIFIERS = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Intended Audience :: System Administrators",
    "Programming Language :: Python",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

short_description = "The Azure IoT Operations extension for Azure CLI."

setup(
    name=PACKAGE_NAME,
    version=VERSION,
    python_requires=">=3.8",
    description=short_description,
    long_description="{} Intended for power users and/or automation of Azure IoT Operations solutions at scale.".format(
        short_description
    ),
    license="MIT",
    author="Microsoft",
    author_email="iotupx@microsoft.com",  # +@digimaun
    url="https://github.com/azure/azure-iot-ops-cli-extension",
    classifiers=CLASSIFIERS,
    packages=find_packages(exclude=["tests", "*.tests", "*.tests.*", "scripts"]),
    package_data={
        EXTENSION_REF_NAME: [
            "azext_metadata.json",
        ]
    },
    install_requires=DEPENDENCIES,
    extras_require=None,
    zip_safe=False,
)
