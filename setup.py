#!/usr/bin/env python
# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# PRIVATE DISTRIBUTION FOR NDA CUSTOMERS ONLY
# --------------------------------------------------------------------------------------------

import re
import os.path
from io import open
from setuptools import setup, find_packages


EXTENSION_REF_NAME = "azext_edge"

# Version extraction inspired from 'requests'
with open(
    os.path.join(EXTENSION_REF_NAME, "constants.py"), "r", encoding="utf-8"
) as fd:
    constants_raw = fd.read()
    VERSION = re.search(
        r'^VERSION\s*=\s*[\'"]([^\'"]*)[\'"]', constants_raw, re.MULTILINE
    ).group(1)
    PACKAGE_NAME = re.search(
        r'^EXTENSION_NAME\s*=\s*[\'"]([^\'"]*)[\'"]', constants_raw, re.MULTILINE
    ).group(1)


if not VERSION:
    raise RuntimeError("Cannot find version information")

if not PACKAGE_NAME:
    raise RuntimeError("Cannot find package information")


# The following dependencies are needed by the IoT extension but used from Az CLI Core.
# 'jmespath',
# 'pyyaml'
# 'knack'

DEPENDENCIES = [
    "rich",
    "kubernetes",
    "tomli",
]

CLASSIFIERS = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Intended Audience :: System Administrators",
    "Programming Language :: Python",
    "Programming Language :: Python :: 3 :: Only",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "License :: OSI Approved :: MIT License",
]

short_description = "The Azure Edge extension for Azure CLI."

setup(
    name=PACKAGE_NAME,
    version=VERSION,
    python_requires=">=3.8",
    description=short_description,
    long_description="{} Intended for power users and/or automation of Azure Edge solutions at scale.".format(
        short_description
    ),
    license="MIT",
    author="Microsoft",
    author_email="iotupx@microsoft.com",  # +@digimaun
    url="https://github.com/azure/azure-edge-cli-extension",
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
