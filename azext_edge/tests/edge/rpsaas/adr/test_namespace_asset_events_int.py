# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List

from ....generators import generate_random_string
from ....helpers import run


def test_namespace_asset_event_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test event operations for namespace assets."""
    # TODO: remove when service is ready
    location = "eastus2euap"

    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    namespace_name = f"ns-{generate_random_string(8)}"
    device_name = f"dev-{generate_random_string(8)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"
    endpoint_name_opcua = f"opcua-{generate_random_string(8)}"
    endpoint_name_onvif = f"onvif-{generate_random_string(8)}"
    asset_name_custom = f"custom-{generate_random_string(8)}"
    asset_name_opcua = f"opcua-{generate_random_string(8)}"
    asset_name_onvif = f"onvif-{generate_random_string(8)}"

    # Event names
    event_name_custom = f"customEvent-{generate_random_string(8)}"
    event_name_opcua = f"opcuaEvent-{generate_random_string(8)}"
    event_name_onvif = f"onvifEvent-{generate_random_string(8)}"

    # Create namespace
    result = run(
        f"az iot ops ns create -n {namespace_name} -g {resource_group} --mi-system-assigned "
        f"--location {location}"
    )
    tracked_resources.append(result["id"])

    # Create Device
    run(
        f"az iot ops ns device create --name {device_name} --namespace {namespace_name} "
        f"-g {resource_group} --instance {instance_name} --template-id dtmi:sample:device;1"
    )

    # Create device endpoints
    for endpoint_name, endpoint_type in [
        (endpoint_name_custom, "custom"),
        (endpoint_name_opcua, "opcua"),
        (endpoint_name_onvif, "onvif")
    ]:
        run(
            f"az iot ops ns device endpoint inbound add {endpoint_type} --device {device_name} "
            f"--namespace {namespace_name} -g {resource_group} --endpoint-name {endpoint_name} "
            f"--endpoint-address http://test-server:8080"
        )

    # Create assets
    run(
        f"az iot ops ns asset custom create --name {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_custom} "
        f"--description 'Custom Asset for Event Testing'"
    )

    run(
        f"az iot ops ns asset opcua create --name {asset_name_opcua} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_opcua} "
        f"--description 'OPC UA Asset for Event Testing'"
    )

    run(
        f"az iot ops ns asset onvif create --name {asset_name_onvif} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_onvif} "
        f"--description 'ONVIF Asset for Event Testing'"
    )

    # Test 1: Add Custom Event
    custom_event = run(
        f"az iot ops ns asset custom event add --asset {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --name {event_name_custom} --event-notifier temperature.alarm "
        f"--event-config '{{\"observabilityMode\": \"log\", \"samplingInterval\": 1000}}' "
        f"--event-dest topic=factory/custom/events qos=1 retain=false ttl=3600"
    )

    assert_event_properties(
        custom_event,
        name=event_name_custom,
        event_notifier="temperature.alarm"
    )

    # Test 2: Add OPC UA Event with full configuration
    opcua_event = run(
        f"az iot ops ns asset opcua event add --asset {asset_name_opcua} --namespace {namespace_name} "
        f"-g {resource_group} --name {event_name_opcua} --event-notifier ns=2;i=1000 "
        f"--event-publish-int 500 --event-queue-size 10 "
        f"--event-filter-type equals --event-filter-clause path=ns=2;i=5000 type=String field=AlarmType "
        f"--event-dest topic=factory/opcua/events qos=2 retain=true ttl=7200"
    )

    assert_event_properties(
        opcua_event,
        name=event_name_opcua,
        event_notifier="ns=2;i=1000"
    )

    # Test 3: Add ONVIF Event
    onvif_event = run(
        f"az iot ops ns asset onvif event add --asset {asset_name_onvif} --namespace {namespace_name} "
        f"-g {resource_group} --name {event_name_onvif} --event-notifier motion.detection "
        f"--event-dest topic=factory/onvif/events qos=1 retain=false ttl=1800"
    )

    assert_event_properties(
        onvif_event,
        name=event_name_onvif,
        event_notifier="motion.detection"
    )

    # Test 4: List events
    custom_events = run(
        f"az iot ops ns asset custom event list --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group}"
    )

    assert len(custom_events) >= 1
    event_names = [ev["name"] for ev in custom_events]
    assert event_name_custom in event_names

    opcua_events = run(
        f"az iot ops ns asset opcua event list --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group}"
    )

    assert len(opcua_events) >= 1
    event_names = [ev["name"] for ev in opcua_events]
    assert event_name_opcua in event_names

    onvif_events = run(
        f"az iot ops ns asset onvif event list --asset {asset_name_onvif} "
        f"--namespace {namespace_name} -g {resource_group}"
    )

    assert len(onvif_events) >= 1
    event_names = [ev["name"] for ev in onvif_events]
    assert event_name_onvif in event_names

    # Test 5: Show event details
    shown_custom_event = run(
        f"az iot ops ns asset custom event show --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_custom}"
    )

    assert_event_properties(
        shown_custom_event,
        name=event_name_custom,
        event_notifier="temperature.alarm"
    )

    shown_opcua_event = run(
        f"az iot ops ns asset opcua event show --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_opcua}"
    )

    assert_event_properties(
        shown_opcua_event,
        name=event_name_opcua,
        event_notifier="ns=2;i=1000"
    )

    shown_onvif_event = run(
        f"az iot ops ns asset onvif event show --asset {asset_name_onvif} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_onvif}"
    )

    assert_event_properties(
        shown_onvif_event,
        name=event_name_onvif,
        event_notifier="motion.detection"
    )

    # Test 6: Update events
    updated_custom_event = run(
        f"az iot ops ns asset custom event update --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_custom} "
        f"--event-notifier temperature.alarm.updated "
        f"--event-config '{{\"observabilityMode\": \"none\", \"samplingInterval\": 2000}}'"
    )

    assert_event_properties(
        updated_custom_event,
        name=event_name_custom,
        event_notifier="temperature.alarm.updated"
    )

    updated_opcua_event = run(
        f"az iot ops ns asset opcua event update --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_opcua} "
        f"--event-notifier ns=3;i=1000 --event-publish-int 1000 "
        f"--event-queue-size 15 --event-filter-type contains"
    )

    assert_event_properties(
        updated_opcua_event,
        name=event_name_opcua,
        event_notifier="ns=3;i=1000"
    )

    updated_onvif_event = run(
        f"az iot ops ns asset onvif event update --asset {asset_name_onvif} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_onvif} "
        f"--event-notifier motion.detection.enhanced"
    )

    assert_event_properties(
        updated_onvif_event,
        name=event_name_onvif,
        event_notifier="motion.detection.enhanced"
    )

    # Test 7: Add event with replace flag
    replaced_custom_event = run(
        f"az iot ops ns asset custom event add --asset {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --name {event_name_custom} --event-notifier temperature.alarm.replaced "
        f"--replace"
    )

    assert_event_properties(
        replaced_custom_event,
        name=event_name_custom,
        event_notifier="temperature.alarm.replaced"
    )

    # Test 8: Remove events
    run(
        f"az iot ops ns asset custom event remove --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_custom}"
    )

    # Verify removal by listing
    remaining_events = run(
        f"az iot ops ns asset custom event list --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group}"
    )

    event_names = [ev["name"] for ev in remaining_events]
    assert event_name_custom not in event_names

    run(
        f"az iot ops ns asset opcua event remove --asset {asset_name_opcua} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_opcua}"
    )

    run(
        f"az iot ops ns asset onvif event remove --asset {asset_name_onvif} "
        f"--namespace {namespace_name} -g {resource_group} --name {event_name_onvif}"
    )


def test_namespace_asset_event_point_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test event point operations for namespace assets."""
    # TODO: remove when service is ready
    location = "eastus2euap"

    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    namespace_name = f"ns-{generate_random_string(8)}"
    device_name = f"dev-{generate_random_string(8)}"
    endpoint_name_custom = f"custom-{generate_random_string(8)}"
    asset_name_custom = f"custom-{generate_random_string(8)}"

    # Event and event point names
    event_name_custom = f"customEvent-{generate_random_string(8)}"
    event_point_name_custom = f"customEventPoint-{generate_random_string(8)}"

    # Create namespace
    result = run(
        f"az iot ops ns create -n {namespace_name} -g {resource_group} --mi-system-assigned "
        f"--location {location}"
    )
    tracked_resources.append(result["id"])

    # Create Device
    run(
        f"az iot ops ns device create --name {device_name} --namespace {namespace_name} "
        f"-g {resource_group} --instance {instance_name} --template-id dtmi:sample:device;1"
    )

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add custom --device {device_name} "
        f"--namespace {namespace_name} -g {resource_group} --endpoint-name {endpoint_name_custom} "
        f"--endpoint-address http://test-server:8080"
    )

    # Create asset
    run(
        f"az iot ops ns asset custom create --name {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --device {device_name} --endpoint-name {endpoint_name_custom}"
    )

    # Create event first
    run(
        f"az iot ops ns asset custom event add --asset {asset_name_custom} --namespace {namespace_name} "
        f"-g {resource_group} --name {event_name_custom} --event-notifier temperature.alarm"
    )

    # Test 1: Add Custom Event Point
    custom_event_point = run(
        f"az iot ops ns asset custom event point add --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --event {event_name_custom} "
        f"--name {event_point_name_custom} --data-source temperature.severity "
        f"--custom-config '{{\"observabilityMode\": \"log\"}}'"
    )

    assert_event_point_properties(
        custom_event_point,
        name=event_point_name_custom,
        data_source="temperature.severity"
    )

    # Test 2: List event points
    custom_event_points = run(
        f"az iot ops ns asset custom event point list --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --event {event_name_custom}"
    )

    assert len(custom_event_points) >= 1
    point_names = [ep["name"] for ep in custom_event_points]
    assert event_point_name_custom in point_names

    # Test 3: Add event point with replace flag
    replaced_custom_event_point = run(
        f"az iot ops ns asset custom event point add --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --event {event_name_custom} "
        f"--name {event_point_name_custom} --data-source temperature.severity.replaced --replace"
    )

    assert_event_point_properties(
        replaced_custom_event_point,
        name=event_point_name_custom,
        data_source="temperature.severity.replaced"
    )

    # Test 4: Remove event point
    run(
        f"az iot ops ns asset custom event point remove --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --event {event_name_custom} "
        f"--name {event_point_name_custom}"
    )

    # Verify removal by listing
    remaining_event_points = run(
        f"az iot ops ns asset custom event point list --asset {asset_name_custom} "
        f"--namespace {namespace_name} -g {resource_group} --event {event_name_custom}"
    )

    point_names = [ep["name"] for ep in remaining_event_points]
    assert event_point_name_custom not in point_names


def assert_event_properties(result, **expected):
    """Verify event properties match expected values."""

    assert result["name"] == expected["name"]

    result_props = result.get("properties", {})

    if "event_notifier" in expected:
        assert result_props.get("eventNotifier") == expected["event_notifier"]

    if "observability_mode" in expected:
        config = result_props.get("eventConfiguration", {})
        assert config.get("observabilityMode") == expected["observability_mode"]

    if "sampling_interval" in expected:
        config = result_props.get("eventConfiguration", {})
        assert config.get("samplingInterval") == expected["sampling_interval"]

    if "publishing_interval" in expected:
        config = result_props.get("eventConfiguration", {})
        assert config.get("publishingInterval") == expected["publishing_interval"]

    if "queue_size" in expected:
        config = result_props.get("eventConfiguration", {})
        assert config.get("queueSize") == expected["queue_size"]

    if "filter_type" in expected:
        config = result_props.get("eventConfiguration", {})
        filter_config = config.get("filter", {})
        assert filter_config.get("type") == expected["filter_type"]

    if "filter_clauses" in expected:
        config = result_props.get("eventConfiguration", {})
        filter_config = config.get("filter", {})
        assert filter_config.get("clauses") == expected["filter_clauses"]

    # Check MQTT destination if present
    if "mqtt_topic" in expected:
        destinations = result_props.get("destinations", [])
        if destinations:
            mqtt_dest = destinations[0].get("mqtt", {})
            assert mqtt_dest.get("topic") == expected["mqtt_topic"]

    if "mqtt_qos" in expected:
        destinations = result_props.get("destinations", [])
        if destinations:
            mqtt_dest = destinations[0].get("mqtt", {})
            assert mqtt_dest.get("qos") == expected["mqtt_qos"]

    if "mqtt_retain" in expected:
        destinations = result_props.get("destinations", [])
        if destinations:
            mqtt_dest = destinations[0].get("mqtt", {})
            assert mqtt_dest.get("retain") == expected["mqtt_retain"]

    if "mqtt_ttl" in expected:
        destinations = result_props.get("destinations", [])
        if destinations:
            mqtt_dest = destinations[0].get("mqtt", {})
            assert mqtt_dest.get("ttl") == expected["mqtt_ttl"]


def assert_event_point_properties(result, **expected):
    """Verify event point properties match expected values."""

    assert result["name"] == expected["name"]

    result_props = result.get("properties", {})

    if "data_source" in expected:
        assert result_props.get("dataSource") == expected["data_source"]

    if "observability_mode" in expected:
        assert result_props.get("observabilityMode") == expected["observability_mode"]

    if "queue_size" in expected:
        config = result_props.get("eventPointConfiguration", {})
        assert config.get("queueSize") == expected["queue_size"]

    if "sampling_interval" in expected:
        config = result_props.get("eventPointConfiguration", {})
        assert config.get("samplingInterval") == expected["sampling_interval"]

    # Check custom configuration for custom assets
    if "custom_config" in expected:
        config = result_props.get("eventPointConfiguration", {})
        custom_config = config.get("customConfiguration")
        if custom_config:
            # Parse JSON if it's a string
            import json
            if isinstance(custom_config, str):
                custom_config = json.loads(custom_config)
            assert custom_config == expected["custom_config"]
