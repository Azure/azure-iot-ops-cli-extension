# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from knack.log import get_logger
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api import DEVICEREGISTRY_API_V1
from .helpers import check_custom_resource_files, BASE_ZIP_PATH, get_file_map, run_bundle_command

logger = get_logger(__name__)


def test_create_bundle_deviceregistry(init_setup, tracked_files):
    """Test for ensuring file names and content. ONLY CHECKS deviceregistry."""
    ops_service = OpsServiceType.deviceregistry.value
    command = f"az iot ops support create-bundle --ops-service {ops_service}"
    walk_result = run_bundle_command(command=command, tracked_files=tracked_files)
    if not walk_result[BASE_ZIP_PATH]["folders"]:
        pytest.skip(f"No bundles created for {ops_service}.")
    file_map = get_file_map(walk_result, ops_service)["aio"]

    check_custom_resource_files(
        file_objs=file_map,
        resource_api=DEVICEREGISTRY_API_V1
    )
    assert set(file_map.keys()).issubset(DEVICEREGISTRY_API_V1.kinds)
