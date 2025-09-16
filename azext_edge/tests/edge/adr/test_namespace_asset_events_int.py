# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
import pytest

from ...generators import generate_random_string
from ...helpers import run
from .namespace_helpers import create_config_file, assert_point_properties, assert_event_properties


pytestmark = pytest.mark.long_running


def test_namespace_custom_asset_event_lifecycle_operations(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """Test complete lifecycle of custom asset event-group and datapoint operations."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"custom-{generate_random_string(8, force_lower=True)}"
    event_name = f"event-{generate_random_string(6, force_lower=True)}"
    datapoint_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add custom --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8000/custom/service' "
        "--endpoint-type custom"
    )

    # Create Custom asset
    asset_custom = run(
        f"az iot ops ns asset custom create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"Custom Device for Event Testing\" --display \"Multi-Sensor Event\" "
        f"--model \"Custom-EV100\" --manufacturer \"CustomDevices\""
    )
    tracked_resources.append(asset_custom["id"])

    # 1. CREATE EVENT
    event_notifier = "temperature.alarm"
    custom_config_path, custom_config = create_config_file(tracked_files)
    event_destinations = "topic=factory/custom/events qos=Qos1 retain=Never ttl=3600"

    event_result = run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier {event_notifier} "
        f"--config {custom_config_path} --destination {event_destinations}"
    )

    assert_event_properties(
        event_result,
        name=event_name,
        event_notifier=event_notifier,
        custom_configuration=custom_config,
    )

    # 2. LIST EVENTS
    events_list = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(events_list) >= 1
    event_names = [ev["name"] for ev in events_list]
    assert event_name in event_names

    # 3. SHOW EVENT
    event_show = run(
        f"az iot ops ns asset custom event-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name}"
    )

    assert_event_properties(
        event_show,
        name=event_name,
        event_notifier=event_notifier
    )

    # 4. UPDATE EVENT
    updated_event_notifier = "temperature.alarm.critical"
    custom_config_path, custom_config = create_config_file(tracked_files)

    updated_event = run(
        f"az iot ops ns asset custom event-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier {updated_event_notifier} "
        f"--config {custom_config_path}"
    )

    assert_event_properties(
        updated_event,
        name=event_name,
        event_notifier=updated_event_notifier,
        custom_configuration=custom_config,
    )

    # 5. CREATE EVENT WITH REPLACE
    replaced_event_notifier = "temperature.alarm.replaced"
    replaced_event = run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier {replaced_event_notifier} "
        f"--replace"
    )

    assert_event_properties(
        replaced_event,
        name=event_name,
        event_notifier=replaced_event_notifier,
    )

    # 6. ADD EVENT DATAPOINT
    datapoint_data_source = "temperature.severity"
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_result = run(
        f"az iot ops ns asset custom event point add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event {event_name} --name {datapoint_name_1} "
        f"--data-source {datapoint_data_source} --config {custom_config_path}"
    )

    assert_point_properties(
        datapoint_result,
        name=datapoint_name_1,
        data_source=datapoint_data_source,
        custom_configuration=custom_config
    )

    # 7. ADD ANOTHER EVENT DATAPOINT
    datapoint_data_source_2 = "temperature.level"
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_result_2 = run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event {event_name} --name {datapoint_name_2} "
        f"--data-source {datapoint_data_source_2} --config {custom_config_path}"
    )

    assert_point_properties(
        datapoint_result_2,
        name=datapoint_name_2,
        data_source=datapoint_data_source_2,
        custom_configuration=custom_config
    )

    # 8. LIST EVENT DATAPOINTS
    datapoints_list = run(
        f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event {event_name}"
    )

    assert len(datapoints_list) >= 2
    datapoint_names = [dp["name"] for dp in datapoints_list]
    assert datapoint_name_1 in datapoint_names
    assert datapoint_name_2 in datapoint_names

    # 9. REPLACE EVENT DATAPOINT
    replaced_datapoint_source = "temperature.severity.replaced"
    replaced_datapoint = run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event {event_name} --name {datapoint_name_1} "
        f"--data-source {replaced_datapoint_source} --replace"
    )

    assert_point_properties(
        replaced_datapoint,
        name=datapoint_name_1,
        data_source=replaced_datapoint_source
    )

    # 10. REMOVE EVENT DATAPOINT
    run(
        f"az iot ops ns asset custom event remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event {event_name} --name {datapoint_name_1}"
    )

    # Verify removal by listing
    remaining_datapoints = run(
        f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event {event_name}"
    )

    remaining_names = [dp["name"] for dp in remaining_datapoints]
    assert datapoint_name_1 not in remaining_names
    assert datapoint_name_2 in remaining_names

    # 11. REMOVE EVENT
    run(
        f"az iot ops ns asset custom event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name}"
    )

    # Verify removal by listing
    remaining_events = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_event_names = [ev["name"] for ev in remaining_events]
    assert event_name not in remaining_event_names


def test_namespace_opcua_asset_event_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of OPC UA asset event-group operations (events only)."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"opcua-{generate_random_string(8, force_lower=True)}"
    event_name = f"event-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.100:4840' "
    )

    # Create OPC UA asset
    asset_opcua = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"OPC UA Device for Event Testing\" --display \"OPC UA Event Server\" "
        f"--model \"OPCUA-EV200\" --manufacturer \"OPCDevices\""
    )
    tracked_resources.append(asset_opcua["id"])

    # 1. CREATE EVENT WITH FULL OPCUA CONFIGURATION
    event_notifier = "ns=2;i=1000"
    event_destinations = "topic=factory/opcua/events qos=Qos0 retain=Keep ttl=7200"
    publishing_interval = 500
    queue_size = 10

    event_result = run(
        f"az iot ops ns asset opcua event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier \"{event_notifier}\" "
        f"--destination {event_destinations} --publish-int {publishing_interval} "
        f"--queue-size {queue_size}"
    )

    assert_event_properties(
        event_result,
        name=event_name,
        event_notifier=event_notifier,
    )

    # 2. LIST EVENTS
    events_list = run(
        f"az iot ops ns asset opcua event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(events_list) >= 1
    event_names = [ev["name"] for ev in events_list]
    assert event_name in event_names

    # 3. SHOW EVENT
    event_show = run(
        f"az iot ops ns asset opcua event-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name}"
    )

    assert_event_properties(
        event_show,
        name=event_name,
        event_notifier=event_notifier
    )

    # 4. UPDATE EVENT
    updated_event_notifier = "ns=3;i=1000"
    updated_publishing_interval = 1000
    updated_queue_size = 15

    updated_event = run(
        f"az iot ops ns asset opcua event-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier \"{updated_event_notifier}\" "
        f"--publish-int {updated_publishing_interval} --queue-size {updated_queue_size} "
    )

    assert_event_properties(
        updated_event,
        name=event_name,
        event_notifier=updated_event_notifier,
    )

    # 5. CREATE EVENT WITH REPLACE
    replaced_event_notifier = "ns=4;i=1000"
    replaced_event = run(
        f"az iot ops ns asset opcua event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier \"{replaced_event_notifier}\" "
        f"--replace"
    )

    assert_event_properties(
        replaced_event,
        name=event_name,
        event_notifier=replaced_event_notifier
    )

    # 6. REMOVE EVENT
    run(
        f"az iot ops ns asset opcua event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name}"
    )

    # Verify removal by listing
    remaining_events = run(
        f"az iot ops ns asset opcua event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_event_names = [ev["name"] for ev in remaining_events]
    assert event_name not in remaining_event_names


def test_namespace_onvif_asset_event_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of ONVIF asset event-group operations (events only)."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"onvif-{generate_random_string(8)}"
    asset_name = f"onvif-{generate_random_string(8, force_lower=True)}"
    event_name = f"event-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add onvif --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8080/onvif/device' "
    )

    # Create ONVIF asset
    asset_onvif = run(
        f"az iot ops ns asset onvif create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"ONVIF Device for Event Testing\" --display \"ONVIF Event Camera\" "
        f"--model \"ONVIF-EV300\" --manufacturer \"ONVIFDevices\""
    )
    tracked_resources.append(asset_onvif["id"])

    # 1. CREATE EVENT
    event_notifier = "motion.detection"
    event_destinations = "topic=factory/onvif/events qos=Qos1 retain=Never ttl=1800"

    event_result = run(
        f"az iot ops ns asset onvif event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier {event_notifier} "
        f"--destination {event_destinations}"
    )

    assert_event_properties(
        event_result,
        name=event_name,
        event_notifier=event_notifier,
    )

    # 2. LIST EVENTS
    events_list = run(
        f"az iot ops ns asset onvif event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(events_list) >= 1
    event_names = [ev["name"] for ev in events_list]
    assert event_name in event_names

    # 3. SHOW EVENT
    event_show = run(
        f"az iot ops ns asset onvif event-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name}"
    )

    assert_event_properties(
        event_show,
        name=event_name,
        event_notifier=event_notifier
    )

    # 4. UPDATE EVENT
    updated_event_notifier = "motion.detection.enhanced"
    updated_event_destinations = "topic=factory/onvif/events/enhanced qos=Qos0 retain=Keep ttl=3600"

    updated_event = run(
        f"az iot ops ns asset onvif event-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier {updated_event_notifier} "
        f"--destination {updated_event_destinations}"
    )

    assert_event_properties(
        updated_event,
        name=event_name,
        event_notifier=updated_event_notifier,
    )

    # 5. CREATE EVENT WITH REPLACE
    replaced_event_notifier = "motion.detection.replaced"
    replaced_event = run(
        f"az iot ops ns asset onvif event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name} --event-notifier {replaced_event_notifier} "
        f"--replace"
    )

    assert_event_properties(
        replaced_event,
        name=event_name,
        event_notifier=replaced_event_notifier
    )

    # 6. REMOVE EVENT
    run(
        f"az iot ops ns asset onvif event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_name}"
    )

    # Verify removal by listing
    remaining_events = run(
        f"az iot ops ns asset onvif event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_event_names = [ev["name"] for ev in remaining_events]
    assert event_name not in remaining_event_names
