# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import os
from time import sleep
from knack.log import get_logger
from azext_edge.edge.common import FileType
from azext_edge.edge.util.common import assemble_nargs_to_dict
from .....generators import generate_random_string
from .....helpers import run

logger = get_logger(__name__)


def test_asset_lifecycle(require_init, tracked_resources):
    rg = require_init["resourceGroup"]
    custom_location = require_init["customLocation"]
    custom_location_rg = require_init["customLocationResourceGroup"]
    cluster_name = require_init["clusterName"]

    # Create an endpoint profile
    endpoint_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    asset_endpoint = run(
        f"az iot ops asset endpoint create -n {endpoint_name} -g {rg} -c {cluster_name} "
        f"--cg {rg} --ta opc.tcp://opcplc-000000:50000"
    )
    tracked_resources.append(asset_endpoint["id"])

    min_asset_name = "test-asset-" + generate_random_string(force_lower=True)[:4]
    data_source = generate_random_string()
    custom_attribute = f"{generate_random_string()}={generate_random_string()}"
    min_asset = run(
        f"az iot ops asset create -n {min_asset_name} -g {rg} -c {cluster_name} --cg {rg} "
        f"--endpoint {endpoint_name} --data data_source={data_source} --custom-attribute {custom_attribute}"
    )
    tracked_resources.append(min_asset["id"])
    assert_asset_props(
        result=min_asset,
        name=min_asset_name,
        cluster_name=cluster_name,
        custom_attributes=custom_attribute,
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

    custom_attribute_key = custom_attribute.split("=")[0]
    update_asset = run(
        f"az iot ops asset update -n {min_asset_name} -g {rg} --disable "
        f"--custom-attribute {custom_attribute_key}=\"\""
    )
    assert_asset_props(
        result=update_asset,
        name=min_asset_name,
        cluster_name=cluster_name,
        custom_attributes=f"{custom_attribute_key}=\"\"",
        custom_location=custom_location,
        disable=True,
        data_points=[{
            "data_source": data_source
        }]
    )

    max_asset_name = "test-asset-" + generate_random_string(force_lower=True)[:4]
    asset_props = {
        "asset_type": generate_random_string(),
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
        "data_publish_int": 800,
        "data_queue_size": 2,
        "data_sample_int": 600,
        "event_publish_int": 400,
        "event_queue_size": 3,
        "event_sample_int": 200,
    }
    event_notifier = generate_random_string()
    command = f"az iot ops asset create -n {max_asset_name} -g {rg} --cl {custom_location} "\
        f"--clg {custom_location_rg} --endpoint {endpoint_name} --event event_notifier={event_notifier} "\
        "sampling_interval 10"
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


def test_asset_sub_point_lifecycle(require_init, tracked_resources, tracked_files):
    rg = require_init["resourceGroup"]
    custom_location = require_init["customLocation"]
    cluster_name = require_init["clusterName"]

    # Create an endpoint profile
    endpoint_name = "test-endpoint-" + generate_random_string(force_lower=True)[:4]
    asset_endpoint = run(
        f"az iot ops asset endpoint create -n {endpoint_name} -g {rg} -c {cluster_name} --cg {rg} "
        "--ta opc.tcp://opcplc-000000:50000"
    )
    tracked_resources.append(asset_endpoint["id"])

    asset_name = "test-asset-" + generate_random_string(force_lower=True)[:4]
    data_source = generate_random_string()
    expected_data_points = [{"data_source": generate_random_string()}]
    asset = run(
        f"az iot ops asset create -n {asset_name} -g {rg} -c {cluster_name} --cg {rg} "
        f"--endpoint {endpoint_name} --data data_source={expected_data_points[0]['data_source']}"
    )
    tracked_resources.append(asset["id"])
    assert_asset_props(
        result=asset,
        name=asset_name,
        cluster_name=cluster_name,
        custom_location=custom_location,
        data_points=[{
            "data_source": data_source
        }]
    )
    assert not asset["properties"]["events"]
    assert len(asset["properties"]["dataPoints"]) == len(expected_data_points)
    assert_sub_point(asset["properties"]["dataPoints"][0], **expected_data_points[0])

    # data points
    expected_data_points.append({
        "capability_id": generate_random_string(),
        "data_source": generate_random_string(),
        "name": generate_random_string(),
        "observability_mode": "log",
        "queue_size": 1,
        "sampling_interval": 30,
    })
    command = f"az iot ops asset data-point add -a {asset_name} -g {rg}"
    for arg, value in expected_data_points[1].items():
        command += f" --{arg.replace('_', '-')} {value}"

    asset_data_points = run(command)
    assert len(asset_data_points) == len(expected_data_points)
    for i in range(len(expected_data_points)):
        assert_sub_point(asset_data_points[i], **expected_data_points[i])

    asset_data_points = run(f"az iot ops asset data-point list -a {asset_name} -g {rg}")
    assert len(asset_data_points) == len(expected_data_points)
    for i in range(len(expected_data_points)):
        assert_sub_point(asset_data_points[i], **expected_data_points[i])

    for file_type in FileType.list():
        data_file_path = run(
            f"az iot ops asset data-point export -a {asset_name} -g {rg} -f {file_type}"
        )["file_path"]
        tracked_files.append(data_file_path)
        assert os.path.exists(data_file_path)

        asset_data_points = run(
            f"az iot ops asset data-point remove -a {asset_name} -g {rg} "
            f"--data-source {expected_data_points[1]['data_source']}"
        )
        assert len(asset_data_points) + 1 == len(expected_data_points)

        asset_data_points = run(
            f"az iot ops asset data-point import -a {asset_name} -g {rg} --input-file {data_file_path}"
        )
        assert len(asset_data_points) == len(expected_data_points)
        assert expected_data_points[1]['data_source'] in [point["dataSource"] for point in asset_data_points]

    # events
    expected_events = [{
        "event_notifier": generate_random_string(),
        "name": generate_random_string(),
        "observability_mode": "log",
        "queue_size": 1,
    }]
    command = f"az iot ops asset event add -a {asset_name} -g {rg}"
    for arg, value in expected_events[0].items():
        command += f" --{arg.replace('_', '-')} {value}"

    asset_events = run(command)
    assert len(asset_events) == len(expected_events)
    expected_events.append({
        "event_notifier": generate_random_string(),
    })
    command = f"az iot ops asset event add -a {asset_name} -g {rg}"
    for arg, value in expected_events[1].items():
        command += f" --{arg.replace('_', '-')} {value}"

    asset_events = run(command)
    assert len(asset_events) == len(expected_events)
    for i in range(len(expected_events)):
        assert_sub_point(asset_events[i], **expected_events[i])

    asset_events = run(f"az iot ops asset event list -a {asset_name} -g {rg}")
    assert len(asset_events) == len(expected_events)
    for i in range(len(expected_events)):
        assert_sub_point(asset_events[i], **expected_events[i])

    for file_type in FileType.list():
        event_file_path = run(
            f"az iot ops asset event export -a {asset_name} -g {rg} -f {file_type}"
        )["file_path"]
        tracked_files.append(event_file_path)
        assert os.path.exists(event_file_path)

        asset_events = run(
            f"az iot ops asset event remove -a {asset_name} -g {rg} "
            f"--event-notifier {expected_events[1]['event_notifier']}"
        )
        assert len(asset_events) + 1 == len(expected_events)

        asset_events = run(
            f"az iot ops asset event import -a {asset_name} -g {rg} --input-file {event_file_path}"
        )
        assert len(asset_events) == len(expected_events)
        assert expected_events[1]['event_notifier'] in [point["eventNotifier"] for point in asset_events]

    second_asset = run(
        f"az iot ops asset create -n {asset_name} -g {rg} -c {cluster_name} --cg {rg} "
        f"--endpoint {endpoint_name} --data-file {data_file_path} --event-file {event_file_path}"
    )
    tracked_resources.append(second_asset["id"])
    assert len(second_asset["properties"]["dataPoints"]) == len(expected_data_points)
    assert_sub_point(second_asset["properties"]["dataPoints"][0], **expected_data_points[0])
    assert len(second_asset["properties"]["events"]) == len(expected_events)
    assert_sub_point(second_asset["properties"]["events"][0], **expected_events[0])


def assert_asset_props(result, **expected):
    assert result["name"] == expected["name"]
    assert result["extendedLocation"]["name"].endswith(expected["custom_location"])

    result_props = result["properties"]
    assert result_props["enabled"] is not expected.get("disable", False)

    if expected.get("asset_type"):
        assert result_props["assetType"] == expected["asset_type"]
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


def assert_sub_point(result, **expected):
    assert result.get("capabilityId") == expected.get("capability_id", expected.get("name"))
    assert result.get("dataSource") == expected.get("data_source")
    assert result.get("eventNotifier") == expected.get("event_notifier")
    assert result.get("name") == expected.get("name")
    # service is weird - sometimes it sets empty observability sometimes not
    assert result.get("observabilityMode", "none") == expected.get("observability_mode", "none")

    key = "dataPointConfiguration"
    if expected.get("event_notifier"):
        key = "eventConfiguration"
    configuration = json.loads(result.get(key, "{}"))
    assert configuration.get("queueSize") == expected.get("queue_size")
    assert configuration.get("samplingInterval") == expected.get("sampling_interval")
