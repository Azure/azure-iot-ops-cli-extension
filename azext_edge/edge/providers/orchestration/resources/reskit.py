# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from ....util import read_file_content
import json


def get_file_config(file_path: str) -> dict:
    config = json.loads(read_file_content(file_path=file_path))
    if "properties" in config:
        config = config["properties"]
    return config
