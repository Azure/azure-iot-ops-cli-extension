# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

# import json
# import os
from time import sleep
from knack.log import get_logger
# from azext_edge.edge.common import FileType
from azext_edge.edge.util.common import assemble_nargs_to_dict
from ....generators import generate_random_string
from ....helpers import run

logger = get_logger(__name__)


def test_asset_lifecycle(require_init, tracked_resources):
    rg = require_init["resourceGroup"]
    instance = require_init["instanceName"]
    custom_location_id = require_init["customLocationId"]

    # Create an endpoint profile
    # endpoint_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    # asset_endpoint = run(
    #     f"az iot ops asset endpoint create -n {endpoint_name} -g {rg} -c {cluster_name} "
    #     f"--cg {rg} --ta opc.tcp://opcplc-000000:50000"
    # )
    # tracked_resources.append(asset_endpoint["id"])
    endpoint_name = "todochangefake"

    min_asset_name = "test-asset-" + generate_random_string(force_lower=True)[:4]
    custom_attribute = f"{generate_random_string()}={generate_random_string()}"
    min_asset = run(
        f"az iot ops asset create -n {min_asset_name} -g {rg} --instance {instance} "
        f"--endpoint {endpoint_name} --custom-attribute {custom_attribute}"
    )
    tracked_resources.append(min_asset["id"])
    assert_asset_props(
        result=min_asset,
        name=min_asset_name,
        custom_attributes=custom_attribute,
        custom_location_id=custom_location_id,
    )

    show_asset = run(
        f"az iot ops asset show -n {min_asset_name} -g {rg}"
    )
    assert_asset_props(
        result=show_asset,
        name=min_asset_name,
        custom_location_id=custom_location_id,
    )

    custom_attribute_key = custom_attribute.split("=")[0]
    update_asset = run(
        f"az iot ops asset update -n {min_asset_name} -g {rg} --disable "
        f"--custom-attribute {custom_attribute_key}=\"\""
    )
    assert_asset_props(
        result=update_asset,
        name=min_asset_name,
        custom_attributes=f"{custom_attribute_key}=\"\"",
        custom_location_id=custom_location_id,
        disable=True,
    )

    max_asset_name = "test-asset-" + generate_random_string(force_lower=True)[:4]
    asset_props = {
        "custom_attribute": f"{generate_random_string()}={generate_random_string()} "
        f"{generate_random_string()}={generate_random_string()}",
        "description": generate_random_string(),
        "display_name": generate_random_string(),
        "documentation_uri": generate_random_string(),
        "external_asset_id": generate_random_string(),
        "hardware_revision": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturer_uri": generate_random_string(),
        "model": generate_random_string(),
        "product_code": generate_random_string(),
        "serial_number": generate_random_string(),
        "software_revision": generate_random_string(),
        "dataset_publish_int": 800,
        "dataset_queue_size": 2,
        "dataset_sample_int": 600,
        "event_publish_int": 400,
        "event_queue_size": 3,
        "event_sample_int": 200,
    }
    event_notifier = generate_random_string()
    event_name = generate_random_string()
    command = f"az iot ops asset create -n {max_asset_name} -g {rg} --instance {instance} "\
        f"--endpoint {endpoint_name} --event event_notifier={event_notifier} "\
        f"sampling_interval 10 name={event_name}"
    for prop in asset_props:
        command += f" --{prop.replace('_', '-')} {asset_props[prop]}"

    max_asset = run(command)
    tracked_resources.append(max_asset["id"])
    assert_asset_props(
        result=max_asset,
        name=max_asset_name,
        custom_location_id=custom_location_id,
        events=[{
            "event_notifier": event_notifier,
            "name": event_name,
            "sampling_interval": 10
        }],
        **asset_props
    )

    run(f"az iot ops asset delete -n {max_asset_name} -g {rg}")
    sleep(30)
    asset_list = run(f"az iot ops asset query --instance {instance}")
    asset_names = [asset["name"] for asset in asset_list]
    assert max_asset_name not in asset_names
    tracked_resources.remove(max_asset["id"])


def assert_asset_props(result, **expected):
    assert result["name"] == expected["name"]
    assert result["extendedLocation"]["name"] == expected["custom_location_id"]

    result_props = result["properties"]
    assert result_props["enabled"] is not expected.get("disable", False)

    if expected.get("custom_attributes"):
        assert result_props["attributes"] is not None
        expected_attributes = assemble_nargs_to_dict(expected["custom_attributes"].split())
        for key, value in expected_attributes.items():
            if value == '""':
                assert key not in result_props["attributes"]
            else:
                assert result_props["attributes"][key] == value
    if expected.get("description"):
        assert result_props["description"] == expected["description"]
    if expected.get("documentation_uri"):
        assert result_props["documentationUri"] == expected["documentation_uri"]
    if expected.get("external_asset_id"):
        assert result_props["externalAssetId"] == expected["external_asset_id"]
    if expected.get("hardware_revision"):
        assert result_props["hardwareRevision"] == expected["hardware_revision"]
    if expected.get("manufacturer"):
        assert result_props["manufacturer"] == expected["manufacturer"]
    if expected.get("manufacturer_uri"):
        assert result_props["manufacturerUri"] == expected["manufacturer_uri"]
    if expected.get("model"):
        assert result_props["model"] == expected["model"]
    if expected.get("product_code"):
        assert result_props["productCode"] == expected["product_code"]
    if expected.get("serial_number"):
        assert result_props["serialNumber"] == expected["serial_number"]
    if expected.get("software_revision"):
        assert result_props["softwareRevision"] == expected["software_revision"]