# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import csv
import json
import os

import yaml

from ...generators import generate_random_string


def parse_exported_file(file_path: str, export_format: str) -> list:
    """Parse an exported file and return the list of items as dicts."""
    with open(file_path, 'r', encoding='utf-8') as f:
        if export_format == "json":
            return json.load(f)
        elif export_format == "yaml":
            return yaml.safe_load(f)
        elif export_format == "csv":
            # CSV DictReader returns flat string values only;
            # sufficient for name/dataSource checks but not nested fields.
            return list(csv.DictReader(f))
    return []


def validate_exported_items(log, items: list, expected_names: list, export_format: str,
                            item_label: str = "item"):
    """Validate exported items have required fields and no incomplete destinations."""
    log.check(f"exported {len(expected_names)} {item_label}s",
              len(items) == len(expected_names), actual=len(items))
    # CSV uses portal-friendly column names instead of "name"
    _csv_name_keys = {"event": "EventName", "datapoint": "TagName"}
    if export_format == "csv":
        name_key = _csv_name_keys.get(item_label, "name")
    else:
        name_key = "name"
    actual_names = {item.get(name_key) for item in items}
    for name in expected_names:
        log.check(f"{name} in export", name in actual_names)
    # Destination structure checks only apply to JSON/YAML where nested dicts are preserved
    if export_format in ("json", "yaml"):
        for item in items:
            name = item.get("name", "<unknown>")
            destinations = item.get("destinations")
            if isinstance(destinations, list):
                for dest in destinations:
                    if isinstance(dest, dict) and "target" in dest:
                        log.check(
                            f"{name} destination has 'configuration'",
                            "configuration" in dest,
                            actual=list(dest.keys())
                        )


def ensure_device_and_endpoint(
    log, instance_name, resource_group, asset_type, endpoint_type,
    endpoint_address, shared_device, endpoint_cache,
):
    """Reuse the shared device and add each endpoint type once via endpoint_cache."""
    log.detail(f"Reusing shared device={shared_device}")

    ep_key = (endpoint_type, endpoint_address)
    if ep_key in endpoint_cache:
        endpoint_name = endpoint_cache[ep_key]
        log.detail(f"Reusing endpoint={endpoint_name}")
        return shared_device, endpoint_name

    endpoint_name = f"{asset_type}-{generate_random_string(8)}"
    endpoint_cmd = (
        f"az iot ops ns device endpoint inbound add {endpoint_type} --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {shared_device} "
        f"--endpoint-address '{endpoint_address}'"
    )
    if endpoint_type == "custom":
        endpoint_cmd += " --endpoint-type custom"
    log.run_command(endpoint_cmd)

    endpoint_cache[ep_key] = endpoint_name
    return shared_device, endpoint_name


def ensure_asset_for_format_tests(
    log, instance_name, resource_group, asset_type, device_name,
    endpoint_name, tracked_resources, test_category, format_test_asset_cache,
):
    """Create or reuse an asset shared across format variants of the same test_category+asset_type."""
    cache_key = (asset_type, test_category)
    if cache_key in format_test_asset_cache:
        asset_name = format_test_asset_cache[cache_key]
        log.detail(f"Reusing shared asset={asset_name}")
        return asset_name

    asset_name = f"{asset_type}-{generate_random_string(8, force_lower=True)}"
    log.run_command(
        f"az iot ops ns asset {asset_type} create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name}",
        tracked_resources=tracked_resources,
    )

    format_test_asset_cache[cache_key] = asset_name
    return asset_name


def validate_export_result(log, export_result, count_key, expected_count, export_format, tracked_files):
    """Validate an export command result and return the exported file path.

    Checks file_path, count key, file extension, and file existence.
    """
    log.check("'file_path' in result", "file_path" in export_result)
    log.check(f"'{count_key}' in result", count_key in export_result)
    log.check(f"{count_key} == {expected_count}", export_result[count_key] == expected_count,
              actual=export_result.get(count_key))
    log.check(f"file is .{export_format}", f".{export_format}" in export_result["file_path"])

    exported_file = export_result["file_path"]
    tracked_files.append(exported_file)
    log.check("exported file exists", os.path.exists(exported_file))
    return exported_file


def verify_items_by_name(log, items, expected_names, field_name=None, field_values=None, label=""):
    """Verify a list of items matches expected names and optionally check a field value per item.

    ``field_values`` is a dict mapping name → expected value (e.g. dataSource paths).
    """
    prefix = f"{label} " if label else ""
    log.check(f"{prefix}{len(expected_names)} items", len(items) == len(expected_names),
              actual=len(items))
    item_dict = {item["name"]: item for item in items}
    for name in expected_names:
        log.check(f"{name} present", name in item_dict)
    if field_name and field_values:
        for name in expected_names:
            expected = field_values[name]
            log.check(f"{name} {field_name}",
                      item_dict[name].get(field_name) == expected,
                      actual=item_dict[name].get(field_name))
    return item_dict


def do_replace_import_test(
    log, step_prepare, step_import, exported_file, tracked_files,
    import_cmd_base, field_name, item_names,
):
    """Run the JSON --replace import test pattern (Steps 8-9 of sub-item tests).

    Modifies the first item's field, imports with --replace, and verifies only
    the first item changed while others remain unchanged.
    """
    with log.step(step_prepare, "Prepare Modified File"):
        with open(exported_file, 'r', encoding='utf-8') as f:
            items = json.load(f)

        modified_items = [items[0]]
        modified_items[0][field_name] = modified_items[0][field_name] + "_modified"

        modified_file = exported_file.replace(".json", "_modified.json")
        tracked_files.append(modified_file)
        with open(modified_file, 'w', encoding='utf-8') as f:
            json.dump(modified_items, f)
        log.detail(f"modified 1 item: {item_names[0]}")

    with log.step(step_import, "Import with --replace"):
        replaced = log.run_command(f"{import_cmd_base} --input-file {modified_file} --replace")

        log.check(f"still {len(item_names)} items", len(replaced) == len(item_names),
                  actual=len(replaced))
        item_dict = {item["name"]: item for item in replaced}
        log.check(f"{item_names[0]} modified", "_modified" in item_dict[item_names[0]][field_name])
        for name in item_names[1:]:
            log.check(f"{name} unchanged", "_modified" not in item_dict[name][field_name])
