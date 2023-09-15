# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
import pytest

from azure.cli.core.azclierror import RequiredArgumentMissingError
from azext_edge.common.utility import assemble_nargs_to_dict

from ....edge.commands_assets import build_configuration, process_data_points, process_events, update_properties

from ...generators import generate_generic_id


@pytest.mark.parametrize("original_configuration", [
    json.dumps({}),
    json.dumps({"publishing_interval": 3, "sampling_interval": 44, "queue_size": 1}),
])
@pytest.mark.parametrize("publishing_interval", [None, 100])
@pytest.mark.parametrize("sampling_interval", [None, 3000])
@pytest.mark.parametrize("queue_size", [None, 4])
def test_build_configuration(original_configuration, publishing_interval, sampling_interval, queue_size):
    new_configuration = build_configuration(
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


@pytest.mark.parametrize("data_points", [
    None,
    [[f"data_source={generate_generic_id()}"]],
    [
        [f"data_source={generate_generic_id()}"],
        [f"data_source={generate_generic_id()}"]
    ],
    [
        [
            f"data_source={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"data_source={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"data_source={generate_generic_id()}",
            "sampling_interval=10",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            f"data_source={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            f"data_source={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
])
def test_process_data_points(data_points):
    expected_result = []
    if data_points:
        for item in data_points:
            parsed_item = assemble_nargs_to_dict(item)

            custom_configuration = {}
            if parsed_item.get("sampling_interval"):
                custom_configuration["samplingInterval"] = int(parsed_item.get("sampling_interval"))
            if parsed_item.get("queue_size"):
                custom_configuration["queueSize"] = int(parsed_item.get("queue_size"))

            if not parsed_item.get("capability_id"):
                parsed_item["capability_id"] = parsed_item.get("name")

            final_item = {
                "capabilityId": parsed_item.get("capability_id"),
                "dataPointConfiguration": json.dumps(custom_configuration),
                "dataSource": parsed_item.get("data_source"),
                "name": parsed_item.get("name"),
                "observabilityMode": parsed_item.get("observability_mode")
            }
            expected_result.append(final_item)

    result = process_data_points(data_points)

    assert result == expected_result


def test_process_data_points_error():
    with pytest.raises(RequiredArgumentMissingError) as e:
        process_data_points(
            [["a=b", "c=d"]]
        )
    assert "missing the data_source" in e.value.error_msg


@pytest.mark.parametrize("events", [
    None,
    [[f"event_notifier={generate_generic_id()}"]],
    [
        [f"event_notifier={generate_generic_id()}"],
        [f"event_notifier={generate_generic_id()}"]
    ],
    [
        [
            f"event_notifier={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"event_notifier={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"event_notifier={generate_generic_id()}",
            "sampling_interval=10",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            f"event_notifier={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            f"event_notifier={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
])
def test_process_events(events):
    expected_result = []
    if events:
        for item in events:
            parsed_item = assemble_nargs_to_dict(item)

            custom_configuration = {}
            if parsed_item.get("sampling_interval"):
                custom_configuration["samplingInterval"] = int(parsed_item.get("sampling_interval"))
            if parsed_item.get("queue_size"):
                custom_configuration["queueSize"] = int(parsed_item.get("queue_size"))

            if not parsed_item.get("capability_id"):
                parsed_item["capability_id"] = parsed_item.get("name")

            final_item = {
                "capabilityId": parsed_item.get("capability_id"),
                "eventConfiguration": json.dumps(custom_configuration),
                "eventNotifier": parsed_item.get("event_notifier"),
                "name": parsed_item.get("name"),
                "observabilityMode": parsed_item.get("observability_mode")
            }
            expected_result.append(final_item)

    result = process_events(events)

    assert result == expected_result


def test_process_events_error():
    with pytest.raises(RequiredArgumentMissingError) as e:
        process_events(
            [["a=b", "c=d"]]
        )
    assert "missing the event_notifier" in e.value.error_msg


@pytest.mark.parametrize("properties", [
    {},
    {
        "assetType": generate_generic_id(),
        "defaultDataPointsConfiguration": "{\"publishingInterval\": \"100\", \"samplingInterval\""
        ": \"10\", \"queueSize\": \"2\"}",
        "defaultEventsConfiguration": "{\"publishingInterval\": \"200\", \"samplingInterval\": "
        "\"20\", \"queueSize\": \"3\"}",
        "description": generate_generic_id(),
        "documentationUri": generate_generic_id(),
        "enabled": True,
        "externalAssetId": generate_generic_id(),
        "hardwareRevision": generate_generic_id(),
        "manufacturer": generate_generic_id(),
        "manufacturerUri": generate_generic_id(),
        "model": generate_generic_id(),
        "productCode": generate_generic_id(),
        "serialNumber": generate_generic_id(),
        "softwareRevision": generate_generic_id(),
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
        "asset_type": generate_generic_id(),
        "description": generate_generic_id(),
        "disabled": True,
        "documentation_uri": generate_generic_id(),
        "external_asset_id": generate_generic_id(),
        "hardware_revision": generate_generic_id(),
        "manufacturer": generate_generic_id(),
        "manufacturer_uri": generate_generic_id(),
        "model": generate_generic_id(),
        "product_code": generate_generic_id(),
        "serial_number": generate_generic_id(),
        "software_revision": generate_generic_id(),
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
    original_properties = json.loads(json.dumps(properties))
    update_properties(
        properties=properties,
        **req
    )

    assert properties.get("assetType") == req.get("asset_type", original_properties.get("assetType"))
    assert properties.get("description") == req.get("description", original_properties.get("description"))
    assert properties.get("enabled") is not req.get("disabled", not original_properties.get("enabled"))
    assert properties.get("documentationUri") == req.get(
        "documentation_uri", original_properties.get("documentationUri")
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

    expected_default_data_points = build_configuration(
        original_configuration=properties.get("defaultDataPointsConfiguration", "{}"),
        publishing_interval=req.get("dp_publishing_interval"),
        sampling_interval=req.get("dp_sampling_interval"),
        queue_size=req.get("dp_queue_size")
    )
    assert properties["defaultDataPointsConfiguration"] == expected_default_data_points

    expected_default_events = build_configuration(
        original_configuration=properties.get("defaultEventsConfiguration", "{}"),
        publishing_interval=req.get("ev_publishing_interval"),
        sampling_interval=req.get("ev_sampling_interval"),
        queue_size=req.get("ev_queue_size")
    )
    assert properties["defaultEventsConfiguration"] == expected_default_events
