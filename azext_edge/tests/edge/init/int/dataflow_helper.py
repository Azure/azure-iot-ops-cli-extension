# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional

from .helper import get_resource_from_partial_id, ResourceKeys


def assert_dataflow_profile_args(
    resource_group: str, init_resources: List[str], dataflow_profile_instances: Optional[int] = None, **_
):
    instance_resources = [res for res in init_resources if res.startswith(ResourceKeys.iot_operations.value)]
    instance_partial_id = instance_resources[0]
    instance_resources = set(instance_resources)

    # Dataflow Profile
    expected_profile_partial_id = f"{instance_partial_id}/dataflowProfiles/profile"
    assert expected_profile_partial_id in instance_resources

    profile = get_resource_from_partial_id(expected_profile_partial_id, resource_group)
    profile_props = profile["properties"]
    assert profile_props["instanceCount"] == (1 or dataflow_profile_instances)
