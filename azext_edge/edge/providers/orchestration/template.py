# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from typing import List, NamedTuple, Union

from ...common import DEFAULT_DATAFLOW_PROFILE


class TemplateVer(NamedTuple):
    commit_id: str
    content: dict
    moniker: str

    def get_component_vers(self) -> dict:
        # Don't need a deep copy here.
        return self.content["variables"]["VERSIONS"].copy()

    @property
    def parameters(self) -> dict:
        return self.content["parameters"]

    def get_resource_defs(self, resource_type: str, first=True) -> Union[List[dict], dict]:
        resources = [resource for resource in self.content["resources"] if resource["type"] == resource_type]
        if first and resources:
            return resources[0]
        return resources

    def copy(self) -> "TemplateVer":
        return TemplateVer(
            commit_id=self.commit_id,
            moniker=self.moniker,
            content=deepcopy(self.content),
        )


M2_ENABLEMENT_TEMPLATE = TemplateVer(
    commit_id="f8fc2737da7d276a8e44f3d3abc74348bc7135c0",
    moniker="v0.6.0-preview",
    content={},
)

M2_INSTANCE_TEMPLATE = TemplateVer(
    commit_id="f8fc2737da7d276a8e44f3d3abc74348bc7135c0",
    moniker="v0.6.0-preview",
    content={},
)


def get_basic_dataflow_profile(profile_name: str = DEFAULT_DATAFLOW_PROFILE, instance_count: int = 1) -> dict:
    return {
        "type": "Microsoft.IoTOperations/instances/dataflowProfiles",
        "apiVersion": "2024-07-01-preview",
        "name": f"[format('{{0}}/{{1}}', parameters('instanceName'), '{profile_name}')]",
        "extendedLocation": {
            "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
            "type": "CustomLocation",
        },
        "properties": {
            "instanceCount": instance_count,
        },
        "dependsOn": [
            "[resourceId('Microsoft.IoTOperations/instances', parameters('instanceName'))]",
            "[resourceId('Microsoft.ExtendedLocation/customLocations', parameters('customLocationName'))]",
        ],
    }


def get_basic_listener(listener_name: str = "") -> dict:
    return {}
