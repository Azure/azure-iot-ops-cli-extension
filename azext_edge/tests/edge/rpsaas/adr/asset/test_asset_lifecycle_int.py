# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from time import sleep
from knack.log import get_logger
from .....generators import generate_random_string
from .....helpers import run

logger = get_logger(__name__)


def test_asset_lifecycle(require_init, tracked_resources):
    rg = require_init["resourceGroup"]
    custom_location = require_init["customLocation"]
    cluster_name = require_init["clusterName"]

    # Create an endpoint profile
    endpoint_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    asset_endpoint = run(
        f"az iot ops asset endpoint create -n {endpoint_name} -g {rg} -c {cluster_name} "
        "--ta opc.tcp://opcplc-000000:50000"
    )
    tracked_resources.append(asset_endpoint["id"])

    min_asset_name = "test-asset-" + generate_random_string(force_lower=True)[:4]
    data_source = generate_random_string()
    min_asset = run(
        f"az iot ops asset create -n {min_asset_name} -g {rg} -c {cluster_name} --endpoint {endpoint_name} "
        f"--data data_source={data_source}"
    )
    tracked_resources.append(min_asset["id"])
    assert_asset_props(
        result=min_asset,
        name=min_asset_name,
        cluster_name=cluster_name,
        custom_location=custom_location,
        data_points=[{
            "data_source": data_source
        }]
    )

    show_asset = run(
        f"az iot ops asset show -n {min_asset_name} -g {rg}"
    )
    assert_asset_props(
        result=show_asset,
        name=min_asset_name,
        cluster_name=cluster_name,
        custom_location=custom_location,
        data_points=[{
            "data_source": data_source
        }]
    )

    update_asset = run(
        f"az iot ops asset update -n {min_asset_name} -g {rg} --disable"
    )
    assert_asset_props(
        result=update_asset,
        name=min_asset_name,
        cluster_name=cluster_name,
        custom_location=custom_location,
        disable=True,
        data_points=[{
            "data_source": data_source
        }]
    )

    max_asset_name = "test-asset-" + generate_random_string(force_lower=True)[:4]
    asset_props = {
        "asset_type": generate_random_string(),
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
        "data_publish_int": 800,
        "data_queue_size": 2,
        "data_sample_int": 600,
        "event_publish_int": 400,
        "event_queue_size": 3,
        "event_sample_int": 200,
    }
    event_notifier = generate_random_string()
    command = f"az iot ops asset create -n {max_asset_name} -g {rg} --cl {custom_location} "\
        f"--endpoint {endpoint_name} --event event_notifier={event_notifier} sampling_interval 10"
    for prop in asset_props:
        command += f" --{prop.replace('_', '-')} {asset_props[prop]}"

    max_asset = run(command)
    tracked_resources.append(max_asset["id"])
    assert_asset_props(
        result=max_asset,
        name=max_asset_name,
        cluster_name=cluster_name,
        custom_location=custom_location,
        events=[{
            "event_notifier": event_notifier,
            "sampling_interval": 10
        }],
        **asset_props
    )

    run(f"az iot ops asset delete -n {max_asset_name} -g {rg}")
    sleep(30)
    asset_list = run(f"az iot ops asset query --cl {custom_location}")
    asset_names = [asset["name"] for asset in asset_list]
    assert max_asset_name not in asset_names
    tracked_resources.remove(max_asset["id"])


def assert_asset_props(result, **expected):
    assert result["name"] == expected["name"]
    assert result["extendedLocation"]["name"].endswith(expected["custom_location"])

    result_props = result["properties"]
    assert result_props["enabled"] is not expected.get("disable", False)

    # if expected.get("data_points"):
    #     data_points = expected["data_points"]

    if expected.get("asset_type"):
        assert result_props["assetType"] == expected["asset_type"]
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
