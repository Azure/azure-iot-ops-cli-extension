# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Protocol, Dict

from ....util import read_file_content


def get_file_config(file_path: str) -> dict:
    config = json.loads(read_file_content(file_path=file_path))
    if "properties" in config:
        config = config["properties"]
    return config


class GetInstanceExtLoc(Protocol):
    def __call__(self, name: str, resource_group_name: str) -> Dict[str, str]:
        ...
