# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
import json
import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError, RequiredArgumentMissingError
from azext_edge.edge.util.common import assemble_nargs_to_dict

from azext_edge.edge.providers.rpsaas.adr.assets import (
    _build_asset_sub_point,
    _build_ordered_csv_conversion_map,
    _build_default_configuration,
    _convert_sub_points_from_csv,
    _convert_sub_points_to_csv,
    _process_asset_sub_points,
    _update_properties
)

from .....generators import generate_random_string


@pytest.mark.parametrize("data_source", [None, generate_random_string()])
@pytest.mark.parametrize("event_notifier", [None, generate_random_string()])
@pytest.mark.parametrize("capability_id", [None, generate_random_string()])
@pytest.mark.parametrize("name", [None, generate_random_string()])
@pytest.mark.parametrize("observability_mode", [None, generate_random_string()])
@pytest.mark.parametrize("queue_size", [None, 20])
@pytest.mark.parametrize("sampling_interval", [None, 33])
def test_build_asset_sub_point(
    data_source, event_notifier, capability_id, name, observability_mode, queue_size, sampling_interval
):
    result = _build_asset_sub_point(
        data_source=data_source,
        event_notifier=event_notifier,
        capability_id=capability_id,
        name=name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval
    )

    assert result["capabilityId"] == (capability_id or name)
    assert result["name"] == name
    assert result["observabilityMode"] == observability_mode

    custom_configuration = {}
    if data_source:
        assert result["dataSource"] == data_source
        assert result["dataPointConfiguration"]
        custom_configuration = json.loads(result["dataPointConfiguration"])
        assert "eventNotifier" not in result
    elif event_notifier:
        assert result["eventNotifier"] == event_notifier
        assert result["eventConfiguration"]
        custom_configuration = json.loads(result["eventConfiguration"])
        assert "dataSource" not in result

    assert custom_configuration.get("samplingInterval") == (
        sampling_interval if data_source or event_notifier else None
    )
    assert custom_configuration.get("queueSize") == (queue_size if data_source or event_notifier else None)


@pytest.mark.parametrize("original_configuration", [
    json.dumps({}),
    json.dumps({"publishing_interval": 3, "sampling_interval": 44, "queue_size": 1}),
])
@pytest.mark.parametrize("publishing_interval", [None, 100])
@pytest.mark.parametrize("sampling_interval", [None, 3000])
@pytest.mark.parametrize("queue_size", [None, 4])
def test_build_default_configuration(original_configuration, publishing_interval, sampling_interval, queue_size):
    new_configuration = _build_default_configuration(
        original_configuration=original_configuration,
        publishing_interval=publishing_interval,
        sampling_interval=sampling_interval,
        queue_size=queue_size
    )
    old_config = json.loads(original_configuration)
    if publishing_interval:
        old_config["publishingInterval"] = publishing_interval
    if sampling_interval:
        old_config["samplingInterval"] = sampling_interval
    if queue_size:
        old_config["queueSize"] = queue_size

    new_config = json.loads(new_configuration)
    assert new_config == old_config


@pytest.mark.parametrize("portal_friendly", [True, False])
@pytest.mark.parametrize("sub_point_type", ["dataPoints", "events"])
def test_build_ordered_csv_conversion_map(sub_point_type, portal_friendly):
    result = _build_ordered_csv_conversion_map(sub_point_type, portal_friendly)

    if sub_point_type == "dataPoints":
        assert result["dataSource"] == ("NodeID" if portal_friendly else "Data Source")
        expected_order = ["dataSource"]
    else:
        assert result["eventNotifier"] == ("EventNotifier" if portal_friendly else "Event Notifier")
        expected_order = ["eventNotifier"]
    expected_order.extend(["name", "queueSize", "observabilityMode"])

    assert result["queueSize"] == ("QueueSize" if portal_friendly else "Queue Size")
    assert result["observabilityMode"] == ("ObservabilityMode" if portal_friendly else "Observability Mode")

    expected_name = "Name"
    if portal_friendly:
        assert "capabilityId" not in result
        expected_name = "EventName"
        if sub_point_type == "dataPoints":
            expected_name = "TagName"
            expected_order.append("samplingInterval")
            assert result["samplingInterval"] == "Sampling Interval Milliseconds"
    else:
        assert result["capabilityId"] == "Capability Id"
        assert result["samplingInterval"] == "Sampling Interval Milliseconds"
        expected_order.append("samplingInterval")
        expected_order.append("capabilityId")

    assert result["name"] == expected_name
    assert list(result.keys()) == expected_order


# TODO: add extra stuffs
@pytest.mark.parametrize("sub_points", [
    [{}, {}],
    [   # portal csv
        {
            "Sampling Interval Milliseconds": "10",
            "QueueSize": "1000",
            "EventName": generate_random_string(),
            "EventNotifier": generate_random_string(),
        }
    ],
    [
        {
            "TagName": generate_random_string(),
            "NodeID": generate_random_string(),
        }
    ],
    [
        {
            "Sampling Interval Milliseconds": "10",
            "TagName": generate_random_string(),
            "NodeID": generate_random_string(),
            "ObservabilityMode": generate_random_string(),
        },
        {
            "Sampling Interval Milliseconds": "10",
            "QueueSize": "1000",
            "EventName": generate_random_string(),
            "EventNotifier": generate_random_string(),
            "ObservabilityMode": generate_random_string(),
        },
        {
            "Sampling Interval Milliseconds": "10",
            "TagName": generate_random_string(),
            "NodeID": generate_random_string(),
            "ObservabilityMode": generate_random_string(),
        }
    ],
    [
        {
            "NodeID": generate_random_string(),
        },
        {
            "EventNotifier": generate_random_string(),
        },
    ],
    [   # non portal csv
        {
            "Sampling Interval Milliseconds": "10",
            "Name": generate_random_string(),
            "Data Source": generate_random_string(),
            "Observability Mode": generate_random_string(),
        },
        {
            "Sampling Interval Milliseconds": "10",
            "Queue Size": "1000",
            "Name": generate_random_string(),
            "Event Notifier": generate_random_string(),
            "Observability Mode": generate_random_string(),
        },
        {
            "Sampling Interval Milliseconds": "10",
            "Name": generate_random_string(),
            "Data Source": generate_random_string(),
            "Observability Mode": generate_random_string(),
        }
    ],
    [
        {
            "Data Source": generate_random_string(),
        },
        {
            "Event Notifier": generate_random_string(),
        },
    ],
])
def test_convert_sub_points_from_csv(sub_points):
    original_copy = deepcopy(sub_points)
    _convert_sub_points_from_csv(sub_points)

    for i in range(len(original_copy)):
        for key in original_copy[i]:
            assert key not in sub_points[i]

        original_name = original_copy[i].get(
            "TagName", original_copy[i].get("EventName", original_copy[i].get("Name"))
        )
        assert sub_points[i].get("name") == original_name
        event_notifier = original_copy[i].get("EventNotifier", original_copy[i].get("Event Notifier"))
        assert sub_points[i].get("eventNotifier") == event_notifier
        assert sub_points[i].get("dataSource") == original_copy[i].get(
            "NodeID", original_copy[i].get("Data Source")
        )
        assert sub_points[i].get("observabilityMode") == original_copy[i].get(
            "ObservabilityMode", original_copy[i].get("Observability Mode")
        )

        if "Sampling Interval Milliseconds" in original_copy[i] or "QueueSize" in original_copy[i]:
            config_key = "eventConfiguration" if event_notifier else "dataPointConfiguration"
            configuration = json.loads(sub_points[i].get(config_key))
            orig_sample = original_copy[i].get("Sampling Interval Milliseconds")
            assert configuration.get("samplingInterval") == (int(orig_sample) if orig_sample else None)
            orig_queue = original_copy[i].get("QueueSize", original_copy[i].get("Queue Size"))
            assert configuration.get("queueSize") == (int(orig_queue) if orig_queue else None)


@pytest.mark.parametrize("default_configuration", [
    {"publishingInterval": 1000, "samplingInterval": 500, "queueSize": 1},
    {"publishingInterval": 1000, "queueSize": 1},
])
@pytest.mark.parametrize("portal_friendly", [False, True])
@pytest.mark.parametrize("sub_points", [
    [{}],
    [
        {
            "configuration": "{\"samplingInterval\": \"100\", \"queueSize\": \"2\"}",
            "capabilityId": generate_random_string(),
            "name": generate_random_string(),
            "observabilityMode": generate_random_string(),
        }
    ],
    [
        {
            "name": generate_random_string(),
            "observabilityMode": generate_random_string(),
        }
    ],
    [
        {
            "configuration": "{\"queueSize\": \"2\"}",
            "capabilityId": generate_random_string(),
            "name": generate_random_string(),
            "observabilityMode": generate_random_string(),
        },
        {
            "configuration": "{\"samplingInterval\": \"100\", \"queueSize\": \"5\"}",
            "capabilityId": generate_random_string(),
            "name": generate_random_string(),
            "observabilityMode": generate_random_string(),
        },
        {
            "configuration": "{\"samplingInterval\": \"100\", \"queueSize\": \"4\"}",
            "capabilityId": generate_random_string(),
            "name": generate_random_string(),
            "observabilityMode": generate_random_string(),
        }
    ],
])
@pytest.mark.parametrize("sub_point_type", ["dataPoints", "events"])
def test_convert_sub_points_to_csv(default_configuration, portal_friendly, sub_points, sub_point_type):
    # do some extra modifications to get valid point and make sure tests dont collide
    sub_points = deepcopy(sub_points)
    key = "dataSource" if sub_point_type == "dataPoints" else "eventNotifier"
    for i in range(len(sub_points)):
        config = sub_points[i].pop("configuration", None)
        if config:
            sub_points[i][f"{sub_point_type[:-1]}Configuration"] = config
        sub_points[i][key] = generate_random_string()

    original_copy = deepcopy(sub_points)
    fieldnames = _convert_sub_points_to_csv(
        sub_points=sub_points,
        sub_point_type=sub_point_type,
        default_configuration=json.dumps(default_configuration),
        portal_friendly=portal_friendly
    )
    csv_map = _build_ordered_csv_conversion_map(sub_point_type, portal_friendly)
    assert fieldnames == list(csv_map.values())

    for i in range(len(sub_points)):
        for key in original_copy[i]:
            assert key not in sub_points[i]
        if portal_friendly:
            assert "capabilityId" not in sub_points[i]
        original_config = json.loads(original_copy[i].get(f"{sub_point_type[:-1]}Configuration", "{}"))
        for asset_key, csv_key in csv_map.items():
            default_config_value = default_configuration.get(asset_key) if portal_friendly else None
            assert sub_points[i][csv_key] == original_copy[i].get(
                asset_key, original_config.get(asset_key, default_config_value)
            )


@pytest.mark.parametrize("required_arg", ["data_source", "event_notifier"])
@pytest.mark.parametrize("sub_points", [
    None,
    [[]],
    [[], []],
    [
        [
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_random_string()}",
            f"name={generate_random_string()}",
            f"observability_mode={generate_random_string()}",
        ]
    ],
    [
        [
            f"name={generate_random_string()}",
            f"observability_mode={generate_random_string()}",
        ]
    ],
    [
        [
            "sampling_interval=10",
            f"capability_id={generate_random_string()}",
            f"name={generate_random_string()}",
            f"observability_mode={generate_random_string()}",
        ],
        [
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_random_string()}",
            f"name={generate_random_string()}",
            f"observability_mode={generate_random_string()}",
        ],
        [
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_random_string()}",
            f"name={generate_random_string()}",
            f"observability_mode={generate_random_string()}",
        ]
    ],
])
def test_process_asset_sub_points(required_arg, sub_points):
    sub_points_copy = sub_points
    if required_arg == "event_notifier" and sub_points_copy:
        for i in range(len(sub_points_copy)):
            processed_point = []
            for arg in sub_points_copy[i]:
                if not (arg.startswith("capability_id") or arg.startswith("sampling_interval")):
                    processed_point.append(arg)
            sub_points_copy[i] = processed_point
    if sub_points_copy:
        # Make a copy to avoid tests from conflicting
        sub_points_copy = sub_points_copy[:]
        for i in range(len(sub_points_copy)):
            sub_points_copy[i] = sub_points_copy[i][:] + [f"{required_arg}={generate_random_string()}"]

    result = _process_asset_sub_points(required_arg, sub_points_copy)
    if sub_points_copy is None:
        sub_points_copy = []
    assert len(result) == len(sub_points_copy)
    for i in range(len(result)):
        expected_item = _build_asset_sub_point(**assemble_nargs_to_dict(sub_points_copy[i]))
        assert result[i] == expected_item


@pytest.mark.parametrize("required_arg", ["data_source", "event_notifier"])
def test_process_asset_sub_points_error(required_arg):
    point_type = "Data point" if required_arg == "data_source" else "Event"
    with pytest.raises(RequiredArgumentMissingError) as e:
        _process_asset_sub_points(
            required_arg,
            [["a=b"]]
        )
    assert e.value.error_msg.startswith(point_type)
    assert f"is missing the {required_arg}" in e.value.error_msg

    invalid_arg = "event_notifier" if required_arg == "data_source" else "data_source"
    with pytest.raises(InvalidArgumentValueError) as e:
        _process_asset_sub_points(
            required_arg,
            [[f"{required_arg}={generate_random_string()}", f"{invalid_arg}={generate_random_string()}"]]
        )
    assert e.value.error_msg.startswith(point_type)
    assert f"does not support {invalid_arg}." in e.value.error_msg


@pytest.mark.parametrize("properties", [
    {},
    {
        "assetType": generate_random_string(),
        "defaultDataPointsConfiguration": "{\"publishingInterval\": \"100\", \"samplingInterval\""
        ": \"10\", \"queueSize\": \"2\"}",
        "defaultEventsConfiguration": "{\"publishingInterval\": \"200\", \"samplingInterval\": "
        "\"20\", \"queueSize\": \"3\"}",
        "description": generate_random_string(),
        "displayName": generate_random_string(),
        "documentationUri": generate_random_string(),
        "enabled": True,
        "externalAssetId": generate_random_string(),
        "hardwareRevision": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturerUri": generate_random_string(),
        "model": generate_random_string(),
        "productCode": generate_random_string(),
        "serialNumber": generate_random_string(),
        "softwareRevision": generate_random_string(),
    }
])
@pytest.mark.parametrize("req", [
    {},
    {
        "disabled": False,
        "dp_queue_size": 4,
        "ev_publishing_interval": 200,
        "ev_sampling_interval": 123,
    },
    {
        "asset_type": generate_random_string(),
        "description": generate_random_string(),
        "disabled": True,
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
        "dp_publishing_interval": 10,
        "dp_sampling_interval": 5,
        "dp_queue_size": 4,
        "ev_publishing_interval": 200,
        "ev_sampling_interval": 123,
        "ev_queue_size": 65,
    }
])
def test_update_properties(properties, req):
    # lazy way of copying to avoid having to make sure we copy possible the lists
    original_properties = deepcopy(properties)
    _update_properties(
        properties=properties,
        **req
    )

    assert properties.get("assetType") == req.get("asset_type", original_properties.get("assetType"))
    assert properties.get("description") == req.get("description", original_properties.get("description"))
    assert properties.get("enabled") is not req.get("disabled", not original_properties.get("enabled"))
    assert properties.get("documentationUri") == req.get(
        "documentation_uri", original_properties.get("documentationUri")
    )
    assert properties.get("displayName") == req.get(
        "display_name", original_properties.get("displayName")
    )
    assert properties.get("externalAssetId") == req.get(
        "external_asset_id", original_properties.get("externalAssetId")
    )
    assert properties.get("hardwareRevision") == req.get(
        "hardware_revision", original_properties.get("hardwareRevision")
    )
    assert properties.get("manufacturer") == req.get("manufacturer", original_properties.get("manufacturer"))
    assert properties.get("manufacturerUri") == req.get("manufacturer_uri", original_properties.get("manufacturerUri"))
    assert properties.get("model") == req.get("model", original_properties.get("model"))
    assert properties.get("productCode") == req.get("product_code", original_properties.get("productCode"))
    assert properties.get("serialNumber") == req.get("serial_number", original_properties.get("serialNumber"))
    assert properties.get("softwareRevision") == req.get(
        "software_revision", original_properties.get("softwareRevision")
    )

    expected_default_data_points = _build_default_configuration(
        original_configuration=properties.get("defaultDataPointsConfiguration", "{}"),
        publishing_interval=req.get("dp_publishing_interval"),
        sampling_interval=req.get("dp_sampling_interval"),
        queue_size=req.get("dp_queue_size")
    )
    assert properties["defaultDataPointsConfiguration"] == expected_default_data_points

    expected_default_events = _build_default_configuration(
        original_configuration=properties.get("defaultEventsConfiguration", "{}"),
        publishing_interval=req.get("ev_publishing_interval"),
        sampling_interval=req.get("ev_sampling_interval"),
        queue_size=req.get("ev_queue_size")
    )
    assert properties["defaultEventsConfiguration"] == expected_default_events
