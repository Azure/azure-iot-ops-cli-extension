# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json

import pytest
from typing import List

from ...generators import generate_random_string
from ..._log import TestLog
from .export_import_helpers import (
    ensure_device_and_endpoint,
    validate_export_result,
)

pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("media", "media", "rtsp://mediaserver.local:554/stream"),
])
def test_namespace_asset_stream_export_import(
    require_namespace_init_session, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str
):
    """Test stream export and import for custom and opcua assets."""
    instance_name = require_namespace_init_session["instanceName"]
    resource_group = require_namespace_init_session["resourceGroup"]
    output_dir = str(tmp_path)
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    stream_name_1 = f"s1-{generate_random_string(6, force_lower=True)}"
    stream_name_2 = f"s2-{generate_random_string(6, force_lower=True)}"
    stream_names = [stream_name_1, stream_name_2]

    with TestLog(
        f"test_namespace_asset_stream_export_import[{asset_type}]", total_steps=6,
    ) as log:

        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        with log.step(2, f"Create {asset_type} Asset"):
            log.run_command(
                f"az iot ops ns asset {asset_type} create --name {asset_name} --instance {instance_name} "
                f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}",
                tracked_resources=tracked_resources,
            )

        cmd_prefix = f"az iot ops ns asset {asset_type} stream"
        cmd_args = f"--asset {asset_name} --instance {instance_name} -g {resource_group}"

        with log.step(3, "Add Streams"):
            for name in stream_names:
                log.run_command(f"{cmd_prefix} add {cmd_args} --name {name}")
            result = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("2 streams added", len(result) == 2, actual=len(result))

        with log.step(4, "Export Streams (JSON)"):
            export_result = log.run_command(f"{cmd_prefix} export {cmd_args} -f json --output-dir {output_dir}")
            exported_file = validate_export_result(
                log, export_result, "stream_count", 2, "json", tracked_files,
            )
            with open(exported_file, 'r', encoding='utf-8') as f:
                items = json.load(f)
            item_dict = {s["name"]: s for s in items}
            for name in stream_names:
                log.check(f"stream {name} exported", name in item_dict)
                log.check(f"stream {name} no destinations",
                          "destinations" not in item_dict[name] or not item_dict[name]["destinations"])

        with log.step(5, "Remove Stream & Verify"):
            log.run_command(f"{cmd_prefix} remove {cmd_args} --name {stream_name_1}")
            result = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("1 stream remains", len(result) == 1, actual=len(result))

        with log.step(6, "Import & Verify"):
            imported = log.run_command(f"{cmd_prefix} import {cmd_args} --input-file {exported_file}")
            imported_dict = {s["name"]: s for s in imported}
            for name in stream_names:
                log.check(f"stream {name} imported", name in imported_dict)
            final = log.run_command(f"{cmd_prefix} list {cmd_args}")
            log.check("final count == 2", len(final) == 2, actual=len(final))
