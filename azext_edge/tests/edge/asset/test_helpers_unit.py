# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
import pytest

from azure.cli.core.azclierror import InvalidArgumentValueError, RequiredArgumentMissingError
from azext_edge.edge.util.common import assemble_nargs_to_dict

from azext_edge.edge.providers.assets import (
    _build_asset_sub_point,
    _build_default_configuration,
    _process_asset_sub_points,
    _update_properties
)

from ...generators import generate_generic_id


@pytest.mark.parametrize("data_source", [None, generate_generic_id()])
@pytest.mark.parametrize("event_notifier", [None, generate_generic_id()])
@pytest.mark.parametrize("capability_id", [None, generate_generic_id()])
@pytest.mark.parametrize("name", [None, generate_generic_id()])
@pytest.mark.parametrize("observability_mode", [None, generate_generic_id()])
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


@pytest.mark.parametrize("required_arg", ["data_source", "event_notifier"])
@pytest.mark.parametrize("sub_points", [
    None,
    [[]],
    [[], []],
    [
        [
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            "sampling_interval=10",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
])
def test_process_asset_sub_points(required_arg, sub_points):
    sub_points_copy = sub_points
    if sub_points_copy:
        # Make a copy to avoid tests from conflicting
        sub_points_copy = sub_points_copy[:]
        for i in range(len(sub_points_copy)):
            sub_points_copy[i] = sub_points_copy[i][:] + [f"{required_arg}={generate_generic_id()}"]

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
            [[f"{required_arg}={generate_generic_id()}", f"{invalid_arg}={generate_generic_id()}"]]
        )
    assert e.value.error_msg.startswith(point_type)
    assert f"does not support {invalid_arg}." in e.value.error_msg


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
