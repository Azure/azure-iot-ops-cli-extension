# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import os

import pytest
from typing import List

from ...generators import generate_random_string
from ..._log import TestLog
from ._export_import_helpers import _ensure_device_and_endpoint

pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


@pytest.mark.parametrize("asset_type, endpoint_type, endpoint_address", [
    ("custom", "custom", "http://192.168.1.100:8000/custom/service"),
    ("media", "media", "rtsp://192.168.1.200:554/stream"),
])
def test_namespace_asset_stream_export_import(
    require_namespace_init, tracked_resources: List[str], tracked_files: List[str], tmp_path,
    shared_device: str, endpoint_cache: dict,
    asset_type: str, endpoint_type: str, endpoint_address: str
):
    """Test stream export and import for custom and media assets."""
    instance_name = require_namespace_init["instanceName"]
    resource_group = require_namespace_init["resourceGroup"]
    output_dir = str(tmp_path)
    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    stream_name_1 = f"str1-{generate_random_string(6, force_lower=True)}"
    stream_name_2 = f"str2-{generate_random_string(6, force_lower=True)}"

    with TestLog(
        f"test_namespace_asset_stream_export_import[{asset_type}]",
        total_steps=6,
    ) as log:

        # Step 1: Ensure Device + Endpoint
        with log.step(1, "Ensure Device + Endpoint"):
            device_name, endpoint_name = _ensure_device_and_endpoint(
                log, instance_name, resource_group, asset_type, endpoint_type,
                endpoint_address, shared_device, endpoint_cache,
            )

        # Step 2: Create asset
        with log.step(2, f"Create {asset_type} Asset"):
            log.run_command(
                f"az iot ops ns asset {asset_type} create --name {asset_name} --instance {instance_name} "
                f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}",
                tracked_resources=tracked_resources,
            )

        # Step 3: Add streams
        with log.step(3, "Add Streams"):
            for stream_name in [stream_name_1, stream_name_2]:
                log.run_command(
                    f"az iot ops ns asset {asset_type} stream add --asset {asset_name} "
                    f"--instance {instance_name} -g {resource_group} --name {stream_name}"
                )
            streams_after_add = log.run_command(
                f"az iot ops ns asset {asset_type} stream list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("2 streams added", len(streams_after_add) == 2, actual=len(streams_after_add))

        # Step 4: Export streams as JSON
        with log.step(4, "Export Streams (JSON)"):
            export_result_json = log.run_command(
                f"az iot ops ns asset {asset_type} stream export --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} -f json "
                f"--output-dir {output_dir}"
            )

            log.check("'file_path' in result", "file_path" in export_result_json)
            log.check("'stream_count' in result", "stream_count" in export_result_json)
            log.check("stream_count == 2", export_result_json["stream_count"] == 2,
                      actual=export_result_json.get("stream_count"))
            log.check("file is .json", ".json" in export_result_json["file_path"])

            exported_file = export_result_json["file_path"]
            tracked_files.append(exported_file)

            log.check("exported file exists", os.path.exists(exported_file))
            with open(exported_file, 'r', encoding='utf-8') as f:
                exported_streams = json.load(f)
            log.check("exported 2 streams", len(exported_streams) == 2,
                      actual=len(exported_streams))
            exported_names = [s["name"] for s in exported_streams]
            log.check(f"{stream_name_1} in export", stream_name_1 in exported_names)
            log.check(f"{stream_name_2} in export", stream_name_2 in exported_names)
            for stream in exported_streams:
                log.check(f"no 'destinations' in {stream['name']}", "destinations" not in stream)

        # Step 5: Remove one stream & verify
        with log.step(5, "Remove Stream & Verify"):
            log.run_command(
                f"az iot ops ns asset {asset_type} stream remove --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --name {stream_name_1}"
            )
            streams_after_remove = log.run_command(
                f"az iot ops ns asset {asset_type} stream list --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group}"
            )
            log.check("1 stream remains", len(streams_after_remove) == 1,
                      actual=len(streams_after_remove))

        # Step 6: Import streams back
        with log.step(6, "Import Streams"):
            imported_streams = log.run_command(
                f"az iot ops ns asset {asset_type} stream import --asset {asset_name} "
                f"--instance {instance_name} -g {resource_group} --input-file {exported_file}"
            )
            log.check("imported 2 streams", len(imported_streams) == 2,
                      actual=len(imported_streams))
            imported_names = [s["name"] for s in imported_streams]
            log.check(f"{stream_name_1} restored", stream_name_1 in imported_names)
            log.check(f"{stream_name_2} restored", stream_name_2 in imported_names)
