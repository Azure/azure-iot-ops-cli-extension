# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List


class ResourceSync:
    def __init__(self, cmd, resource_group_name: str, instance_name: str):
        self.cmd = cmd
        self.resource_group_name = resource_group_name
        self.instance_name = instance_name

    def enable(self):
        pass

    def disable(self):
        pass

    def list(self) -> List[dict]:
        return []
