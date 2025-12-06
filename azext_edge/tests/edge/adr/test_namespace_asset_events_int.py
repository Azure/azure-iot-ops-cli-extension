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
    event_group_name = f"event-group-{generate_random_string(6, force_lower=True)}"
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

    # 1. CREATE EVENT GROUP
    data_source = "temperature.alarm"
    custom_config_path, custom_config = create_config_file(tracked_files)
    event_destinations = "topic=factory/custom/events qos=Qos1 retain=Never ttl=3600"

    event_result = run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {data_source} "
        f"--config {custom_config_path} --destination {event_destinations}"
    )

    assert_event_properties(
        event_result,
        name=event_group_name,
        data_source=data_source,
        custom_configuration=custom_config,
    )

    # 2. LIST EVENT GROUPS
    event_groups_list = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(event_groups_list) >= 1
    event_group_names = [eg["name"] for eg in event_groups_list]
    assert event_group_name in event_group_names

    # 3. SHOW EVENT GROUP
    event_show = run(
        f"az iot ops ns asset custom event-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name}"
    )

    assert_event_properties(
        event_show,
        name=event_group_name,
        data_source=data_source
    )

    # 4. UPDATE EVENT GROUP
    updated_data_source = "temperature.alarm.critical"
    custom_config_path, custom_config = create_config_file(tracked_files)

    updated_event = run(
        f"az iot ops ns asset custom event-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {updated_data_source} "
        f"--config {custom_config_path}"
    )

    assert_event_properties(
        updated_event,
        name=event_group_name,
        data_source=updated_data_source,
        custom_configuration=custom_config,
    )

    # 5. CREATE EVENT WITH REPLACE
    replaced_data_source = "temperature.alarm.replaced"
    replaced_event = run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {replaced_data_source} "
        f"--replace"
    )

    assert_event_properties(
        replaced_event,
        name=event_group_name,
        data_source=replaced_data_source,
    )

    # 6. ADD EVENT DATAPOINT
    datapoint_data_source = "temperature.severity"
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_result = run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_1} "
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
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_2} "
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
        f"-g {resource_group} --event-group {event_group_name}"
    )

    assert len(datapoints_list) >= 2
    datapoint_names = [dp["name"] for dp in datapoints_list]
    assert datapoint_name_1 in datapoint_names
    assert datapoint_name_2 in datapoint_names

    # 9. REPLACE EVENT DATAPOINT
    replaced_datapoint_source = "temperature.severity.replaced"
    replaced_datapoint = run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_1} "
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
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_1}"
    )

    # Verify removal by listing
    remaining_datapoints = run(
        f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name}"
    )

    remaining_names = [dp["name"] for dp in remaining_datapoints]
    assert datapoint_name_1 not in remaining_names
    assert datapoint_name_2 in remaining_names

    # 11. REMOVE EVENT
    run(
        f"az iot ops ns asset custom event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name}"
    )

    # Verify removal by listing
    remaining_event_groups = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_event_group_names = [eg["name"] for eg in remaining_event_groups]
    assert event_group_name not in remaining_event_group_names


def test_namespace_opcua_asset_event_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of OPC UA asset event-group operations (events only)."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"opcua-{generate_random_string(8, force_lower=True)}"
    event_group_name = f"event-group-{generate_random_string(6, force_lower=True)}"

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
    data_source = "ns=2;i=1000"
    event_destinations = "topic=factory/opcua/events qos=Qos0 retain=Keep ttl=7200"
    publishing_interval = 500
    queue_size = 10

    event_result = run(
        f"az iot ops ns asset opcua event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source \"{data_source}\" "
        f"--destination {event_destinations} --publish-int {publishing_interval} "
        f"--queue-size {queue_size}"
    )

    assert_event_properties(
        event_result,
        name=event_group_name,
        data_source=data_source,
    )

    # 2. LIST EVENT GROUPS
    event_groups_list = run(
        f"az iot ops ns asset opcua event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(event_groups_list) >= 1
    event_group_names = [eg["name"] for eg in event_groups_list]
    assert event_group_name in event_group_names

    # 3. SHOW EVENT GROUP
    event_show = run(
        f"az iot ops ns asset opcua event-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name}"
    )

    assert_event_properties(
        event_show,
        name=event_group_name,
        data_source=data_source
    )

    # 4. UPDATE EVENT GROUP
    updated_data_source = "ns=3;i=1000"
    updated_publishing_interval = 1000
    updated_queue_size = 15

    updated_event = run(
        f"az iot ops ns asset opcua event-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source \"{updated_data_source}\" "
        f"--publish-int {updated_publishing_interval} --queue-size {updated_queue_size} "
    )

    assert_event_properties(
        updated_event,
        name=event_group_name,
        data_source=updated_data_source,
    )

    # 5. CREATE EVENT GROUP WITH REPLACE
    replaced_data_source = "ns=4;i=1000"
    replaced_event = run(
        f"az iot ops ns asset opcua event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source \"{replaced_data_source}\" "
        f"--replace"
    )

    assert_event_properties(
        replaced_event,
        name=event_group_name,
        data_source=replaced_data_source
    )

    # 6. REMOVE EVENT GROUP
    run(
        f"az iot ops ns asset opcua event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name}"
    )

    # Verify removal by listing
    remaining_event_groups = run(
        f"az iot ops ns asset opcua event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_event_group_names = [eg["name"] for eg in remaining_event_groups]
    assert event_group_name not in remaining_event_group_names


def test_namespace_onvif_asset_event_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of ONVIF asset event-group operations (events only)."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"onvif-{generate_random_string(8)}"
    asset_name = f"onvif-{generate_random_string(8, force_lower=True)}"
    event_group_name = f"event-group-{generate_random_string(6, force_lower=True)}"

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

    # 1. CREATE EVENT GROUP
    data_source = "motion.detection"
    event_destinations = "topic=factory/onvif/events qos=Qos1 retain=Never ttl=1800"

    event_result = run(
        f"az iot ops ns asset onvif event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {data_source} "
        f"--destination {event_destinations}"
    )

    assert_event_properties(
        event_result,
        name=event_group_name,
        data_source=data_source,
    )

    # 2. LIST EVENT GROUPS
    event_groups_list = run(
        f"az iot ops ns asset onvif event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(event_groups_list) >= 1
    event_group_names = [ev["name"] for ev in event_groups_list]
    assert event_group_name in event_group_names

    # 3. SHOW EVENT GROUP
    event_show = run(
        f"az iot ops ns asset onvif event-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name}"
    )

    assert_event_properties(
        event_show,
        name=event_group_name,
        data_source=data_source
    )

    # 4. UPDATE EVENT GROUP
    updated_data_source = "motion.detection.enhanced"
    updated_event_destinations = "topic=factory/onvif/events/enhanced qos=Qos0 retain=Keep ttl=3600"

    updated_event = run(
        f"az iot ops ns asset onvif event-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {updated_data_source} "
        f"--destination {updated_event_destinations}"
    )

    assert_event_properties(
        updated_event,
        name=event_group_name,
        data_source=updated_data_source,
    )

    # 5. CREATE EVENT WITH REPLACE
    replaced_data_source = "motion.detection.replaced"
    replaced_event = run(
        f"az iot ops ns asset onvif event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {replaced_data_source} "
        f"--replace"
    )

    assert_event_properties(
        replaced_event,
        name=event_group_name,
        data_source=replaced_data_source
    )

    # 6. REMOVE EVENT GROUP
    run(
        f"az iot ops ns asset onvif event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name}"
    )

    # Verify removal by listing
    remaining_event_groups = run(
        f"az iot ops ns asset onvif event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_event_group_names = [ev["name"] for ev in remaining_event_groups]
    assert event_group_name not in remaining_event_group_names


def test_namespace_sse_asset_event_lifecycle_operations(require_init, tracked_resources: List[str]):
    """Test complete lifecycle of SSE asset event-group operations (events only)."""
    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"sse-{generate_random_string(8)}"
    asset_name = f"sse-{generate_random_string(8, force_lower=True)}"
    event_group_name = f"event-group-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create device endpoint
    run(
        f"az iot ops ns device endpoint inbound add sse --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'https://events.example.com/stream'"
    )

    # Create SSE asset
    asset_sse = run(
        f"az iot ops ns asset sse create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"SSE Event Stream for Testing\" --display \"SSE Event Stream\" "
        f"--model \"SSE-EV100\" --manufacturer \"EventStreamDevices\""
    )
    tracked_resources.append(asset_sse["id"])

    # 1. CREATE EVENT GROUP
    data_source = "/events/alerts"
    event_destinations = "topic=factory/sse/events qos=Qos1 retain=Never ttl=1800"

    event_result = run(
        f"az iot ops ns asset sse event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {data_source} "
        f"--destination {event_destinations}"
    )

    assert_event_properties(
        event_result,
        name=event_group_name,
        data_source=data_source,
    )

    # 2. LIST EVENT GROUPS
    event_groups_list = run(
        f"az iot ops ns asset sse event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    assert len(event_groups_list) >= 1
    event_group_names = [ev["name"] for ev in event_groups_list]
    assert event_group_name in event_group_names

    # 3. SHOW EVENT GROUP
    event_show = run(
        f"az iot ops ns asset sse event-group show --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name}"
    )

    assert_event_properties(
        event_show,
        name=event_group_name,
        data_source=data_source
    )

    # 4. UPDATE EVENT GROUP
    updated_data_source = "/events/alerts/critical"
    updated_event_destinations = "topic=factory/sse/events/critical qos=Qos0 retain=Keep ttl=3600"

    updated_event = run(
        f"az iot ops ns asset sse event-group update --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {updated_data_source} "
        f"--destination {updated_event_destinations}"
    )

    assert_event_properties(
        updated_event,
        name=event_group_name,
        data_source=updated_data_source,
    )

    # 5. CREATE EVENT WITH REPLACE
    replaced_data_source = "/events/alerts/replaced"
    replaced_event = run(
        f"az iot ops ns asset sse event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} --data-source {replaced_data_source} "
        f"--replace"
    )

    assert_event_properties(
        replaced_event,
        name=event_group_name,
        data_source=replaced_data_source
    )

    # 6. ADD INDIVIDUAL EVENTS TO EVENT GROUP
    datapoint_name_1 = f"event-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"event-{generate_random_string(6, force_lower=True)}"
    datapoint_data_source = "/events/temperature/severity"
    event_destinations = "topic=factory/sse/temperature/severity qos=Qos1 retain=Keep ttl=1800"

    # Add first individual event (SSE uses event destinations, not sampling intervals)
    datapoint_result = run(
        f"az iot ops ns asset sse event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_1} "
        f"--data-source {datapoint_data_source} --destination {event_destinations}"
    )

    assert_point_properties(
        datapoint_result,
        name=datapoint_name_1,
        data_source=datapoint_data_source,
    )

    # 7. ADD SECOND INDIVIDUAL EVENT
    datapoint_2_data_source = "/events/pressure/alert"
    datapoint_2_destinations = "topic=factory/sse/pressure/alert qos=Qos0 retain=Never ttl=900"

    datapoint_2_result = run(
        f"az iot ops ns asset sse event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_2} "
        f"--data-source {datapoint_2_data_source} --destination {datapoint_2_destinations}"
    )

    assert_point_properties(
        datapoint_2_result,
        name=datapoint_name_2,
        data_source=datapoint_2_data_source,
    )

    # 8. LIST INDIVIDUAL EVENTS IN EVENT GROUP
    events_list = run(
        f"az iot ops ns asset sse event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name}"
    )

    event_names = [ev["name"] for ev in events_list]
    assert datapoint_name_1 in event_names
    assert datapoint_name_2 in event_names
    assert len(events_list) >= 2

    # 9. UPDATE INDIVIDUAL EVENT WITH REPLACE
    updated_datapoint_destinations = "topic=factory/sse/temperature/updated qos=Qos0 retain=Never ttl=600"

    updated_datapoint = run(
        f"az iot ops ns asset sse event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_1} "
        f"--data-source {datapoint_data_source} --destination {updated_datapoint_destinations} "
        f"--replace"
    )

    assert_point_properties(
        updated_datapoint,
        name=datapoint_name_1,
        data_source=datapoint_data_source,
    )

    # 10. REMOVE INDIVIDUAL EVENT
    run(
        f"az iot ops ns asset sse event remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_1}"
    )

    # Verify individual event removal
    remaining_events_after_remove = run(
        f"az iot ops ns asset sse event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name}"
    )

    remaining_event_names = [ev["name"] for ev in remaining_events_after_remove]
    assert datapoint_name_1 not in remaining_event_names
    assert datapoint_name_2 in remaining_event_names

    # 11. REMOVE EVENT GROUP
    run(
        f"az iot ops ns asset sse event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name}"
    )

    # Verify removal by listing
    remaining_event_groups = run(
        f"az iot ops ns asset sse event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    remaining_event_group_names = [ev["name"] for ev in remaining_event_groups]
    assert event_group_name not in remaining_event_group_names


def test_namespace_asset_event_export_import_operations(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """Test export and import operations for event groups and events."""
    import os
    import json

    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"custom-{generate_random_string(8, force_lower=True)}"
    event_group_name_1 = f"eg1-{generate_random_string(6, force_lower=True)}"
    event_group_name_2 = f"eg2-{generate_random_string(6, force_lower=True)}"
    event_name_1 = f"ev1-{generate_random_string(6, force_lower=True)}"
    event_name_2 = f"ev2-{generate_random_string(6, force_lower=True)}"

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
        f"--description \"Custom Device for Export/Import Testing\" --display \"Export Import Test Asset\" "
        f"--model \"Custom-EI100\" --manufacturer \"CustomDevices\""
    )
    tracked_resources.append(asset_custom["id"])

    # 1. CREATE EVENT GROUPS WITH EVENTS
    custom_config_path, custom_config = create_config_file(tracked_files)

    # Create first event group
    run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1} --data-source event.source.1 "
        f"--config {custom_config_path}"
    )

    # Create second event group
    run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_2} --data-source event.source.2 "
        f"--config {custom_config_path}"
    )

    # Add events to first event group
    run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --name {event_name_1} "
        f"--data-source event.data.1 --config {custom_config_path}"
    )
    run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --name {event_name_2} "
        f"--data-source event.data.2 --config {custom_config_path}"
    )

    # 2. EXPORT EVENT GROUPS
    output_dir = "/tmp"
    export_result = run(
        f"az iot ops ns asset custom event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format json --od {output_dir} --replace"
    )

    assert "file_path" in export_result
    export_file_path = export_result["file_path"]
    tracked_files.append(export_file_path)

    # Verify the exported file exists and contains the event groups
    assert os.path.exists(export_file_path)
    with open(export_file_path, "r") as f:
        exported_data = json.load(f)

    exported_group_names = [eg["name"] for eg in exported_data]
    assert event_group_name_1 in exported_group_names
    assert event_group_name_2 in exported_group_names

    # 3. EXPORT EVENTS FROM EVENT GROUP
    events_export_result = run(
        f"az iot ops ns asset custom event export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --format json --od {output_dir} --replace"
    )

    assert "file_path" in events_export_result
    events_export_file_path = events_export_result["file_path"]
    tracked_files.append(events_export_file_path)

    # Verify the exported events file
    assert os.path.exists(events_export_file_path)
    with open(events_export_file_path, "r") as f:
        exported_events = json.load(f)

    exported_event_names = [ev["name"] for ev in exported_events]
    assert event_name_1 in exported_event_names
    assert event_name_2 in exported_event_names

    # 4. IMPORT EVENTS INTO EVENT GROUP
    # Create a new event in the import file
    new_event_name = f"imported-{generate_random_string(6, force_lower=True)}"
    import_events = exported_events.copy()
    import_events.append({
        "name": new_event_name,
        "dataSource": "imported.event.source",
        "eventConfiguration": "{}"
    })

    # Write import file
    import_file_path = f"/tmp/import_events_{generate_random_string(8)}.json"
    tracked_files.append(import_file_path)
    with open(import_file_path, "w") as f:
        json.dump(import_events, f)

    # Import events
    run(
        f"az iot ops ns asset custom event import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --if {import_file_path}"
    )

    # Verify the imported events
    events_list = run(
        f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1}"
    )

    event_names = [ev["name"] for ev in events_list]
    assert event_name_1 in event_names
    assert event_name_2 in event_names
    assert new_event_name in event_names

    # 5. IMPORT EVENT GROUPS
    # Create a new event group in the import file
    new_event_group_name = f"imported-eg-{generate_random_string(6, force_lower=True)}"
    import_event_groups = exported_data.copy()
    import_event_groups.append({
        "name": new_event_group_name,
        "dataSource": "imported.group.source",
        "eventGroupConfiguration": "{}",
        "defaultDestinations": []
    })

    # Write import file
    import_groups_file_path = f"/tmp/import_event_groups_{generate_random_string(8)}.json"
    tracked_files.append(import_groups_file_path)
    with open(import_groups_file_path, "w") as f:
        json.dump(import_event_groups, f)

    # Import event groups
    run(
        f"az iot ops ns asset custom event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {import_groups_file_path}"
    )

    # Verify the imported event groups
    event_groups_list = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )

    group_names = [eg["name"] for eg in event_groups_list]
    assert event_group_name_1 in group_names
    assert event_group_name_2 in group_names
    assert new_event_group_name in group_names

    # 6. VERIFY EVENTS ARE STRIPPED DURING EVENT GROUP EXPORT
    # The exported event groups should not contain events (similar to datasets not containing dataPoints)
    for eg in exported_data:
        assert "events" not in eg or not eg.get("events"), \
            "Events should be stripped during event-group export"

    # 7. TEST REMOVE AND RESTORE CYCLE FOR EVENT GROUPS
    # First, re-export to get fresh data that includes both original event groups
    reexport_result = run(
        f"az iot ops ns asset custom event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format json --od {output_dir} --replace"
    )
    reexport_file_path = reexport_result["file_path"]
    tracked_files.append(reexport_file_path)

    # Read the re-exported data to verify eg1 is still there
    with open(reexport_file_path, "r") as f:
        reexported_data = json.load(f)
    reexported_group_names = [eg["name"] for eg in reexported_data]
    assert event_group_name_1 in reexported_group_names, \
        f"Event group {event_group_name_1} should be in re-exported data before removal"

    # Remove the first event group
    run(
        f"az iot ops ns asset custom event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1}"
    )

    # Verify removal
    event_groups_after_remove = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    group_names_after_remove = [eg["name"] for eg in event_groups_after_remove]
    assert event_group_name_1 not in group_names_after_remove

    # Import the re-exported file to restore (this file contains eg1 from before removal)
    run(
        f"az iot ops ns asset custom event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {reexport_file_path}"
    )

    # Verify event group is restored (without events, since they were stripped)
    event_groups_after_restore = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    group_names_after_restore = [eg["name"] for eg in event_groups_after_restore]
    assert event_group_name_1 in group_names_after_restore

    # Verify events are empty for restored event group (since they were stripped during export)
    events_after_restore = run(
        f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1}"
    )
    assert len(events_after_restore) == 0, \
        "Restored event group should have no events (stripped during export)"

    # 8. TEST REMOVE AND RESTORE CYCLE FOR INDIVIDUAL EVENTS
    # First, add events back to the restored event group for this test
    run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --name {event_name_1} "
        f"--data-source event.data.restored.1"
    )

    # Export events again
    events_export_for_restore = run(
        f"az iot ops ns asset custom event export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --format json --od {output_dir} --replace"
    )
    events_restore_file = events_export_for_restore["file_path"]
    tracked_files.append(events_restore_file)

    # Remove the event
    run(
        f"az iot ops ns asset custom event remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --name {event_name_1}"
    )

    # Verify removal
    events_after_event_remove = run(
        f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1}"
    )
    event_names_after_remove = [ev["name"] for ev in events_after_event_remove]
    assert event_name_1 not in event_names_after_remove

    # Import to restore
    run(
        f"az iot ops ns asset custom event import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --if {events_restore_file}"
    )

    # Verify event is restored
    events_after_event_restore = run(
        f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1}"
    )
    event_names_after_restore = [ev["name"] for ev in events_after_event_restore]
    assert event_name_1 in event_names_after_restore

    # 9. TEST IMPORT VALIDATION (FAILURE) - Invalid event group configuration
    import_file_invalid_eg = f"/tmp/import_event_groups_invalid_{generate_random_string(8)}.json"
    tracked_files.append(import_file_invalid_eg)

    # Provide a malformed JSON string for configuration to trigger CLI validation error
    invalid_eg_payload = [{
        "name": "invalid_eg",
        "dataSource": "event/invalid",
        "eventGroupConfiguration": "{ this is not valid json }"
    }]

    with open(import_file_invalid_eg, "w") as f:
        json.dump(invalid_eg_payload, f)

    # Expect failure
    run(
        f"az iot ops ns asset custom event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {import_file_invalid_eg}",
        expect_failure=True
    )

    # 10. TEST IMPORT VALIDATION (FAILURE) - Invalid event configuration
    import_file_invalid_ev = f"/tmp/import_events_invalid_{generate_random_string(8)}.json"
    tracked_files.append(import_file_invalid_ev)

    # Provide a malformed JSON string for configuration to trigger CLI validation error
    invalid_ev_payload = [{
        "name": "invalid_ev",
        "dataSource": "event/invalid",
        "eventConfiguration": "{ this is not valid json }"
    }]

    with open(import_file_invalid_ev, "w") as f:
        json.dump(invalid_ev_payload, f)

    # Expect failure
    run(
        f"az iot ops ns asset custom event import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --if {import_file_invalid_ev}",
        expect_failure=True
    )


def test_namespace_opcua_event_import_export_operations(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """Test OPC UA event-group import and export operations with OPC UA-specific configurations."""
    import os
    import json

    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"opcua-{generate_random_string(8)}"
    asset_name = f"opcua-{generate_random_string(8, force_lower=True)}"
    asset_name_2 = f"opcua-2-{generate_random_string(8, force_lower=True)}"
    event_group_name_1 = f"eg1-{generate_random_string(6, force_lower=True)}"
    event_group_name_2 = f"eg2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create OPC UA device endpoint
    run(
        f"az iot ops ns device endpoint inbound add opcua --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'opc.tcp://192.168.1.200:4840/OPCUA/Server'"
    )

    # Create OPC UA asset 1
    asset_1 = run(
        f"az iot ops ns asset opcua create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"OPC UA Device for Event Export/Import Testing\""
    )
    tracked_resources.append(asset_1["id"])

    # 1. CREATE EVENT GROUPS WITH OPC UA-SPECIFIC CONFIGURATIONS
    # OPC UA event groups support publishing interval, queue size, etc.
    publishing_interval_1 = 500
    queue_size_1 = 10
    data_source_1 = "ns=2;i=1001"

    run(
        f"az iot ops ns asset opcua event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1} --data-source \"{data_source_1}\" "
        f"--publish-int {publishing_interval_1} --queue-size {queue_size_1}"
    )

    publishing_interval_2 = 1000
    queue_size_2 = 20
    data_source_2 = "ns=2;i=1002"

    run(
        f"az iot ops ns asset opcua event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_2} --data-source \"{data_source_2}\" "
        f"--publish-int {publishing_interval_2} --queue-size {queue_size_2}"
    )

    # 2. EXPORT EVENT GROUPS
    output_dir = "/tmp"
    export_result = run(
        f"az iot ops ns asset opcua event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format json --od {output_dir} --replace"
    )

    assert "file_path" in export_result
    export_file_path = export_result["file_path"]
    tracked_files.append(export_file_path)

    # Verify the exported file exists and contains the event groups
    assert os.path.exists(export_file_path)
    with open(export_file_path, "r") as f:
        exported_data = json.load(f)

    assert len(exported_data) == 2
    exported_group_names = [eg["name"] for eg in exported_data]
    assert event_group_name_1 in exported_group_names
    assert event_group_name_2 in exported_group_names

    # 3. VERIFY OPC UA-SPECIFIC CONFIGURATION IS PRESERVED IN EXPORT
    for eg in exported_data:
        if eg["name"] == event_group_name_1:
            config = json.loads(eg["eventGroupConfiguration"])
            assert config.get("publishingInterval") == publishing_interval_1
            assert config.get("queueSize") == queue_size_1
        elif eg["name"] == event_group_name_2:
            config = json.loads(eg["eventGroupConfiguration"])
            assert config.get("publishingInterval") == publishing_interval_2
            assert config.get("queueSize") == queue_size_2

    # 4. CREATE SECOND OPC UA ASSET FOR CROSS-ASSET IMPORT TEST
    asset_2 = run(
        f"az iot ops ns asset opcua create --name {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"OPC UA Device 2 for Import Testing\""
    )
    tracked_resources.append(asset_2["id"])

    # 5. IMPORT EVENT GROUPS TO SECOND ASSET
    run(
        f"az iot ops ns asset opcua event-group import --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --if {export_file_path}"
    )

    # Verify event groups are imported to second asset
    event_groups_asset_2 = run(
        f"az iot ops ns asset opcua event-group list --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group}"
    )

    group_names_asset_2 = [eg["name"] for eg in event_groups_asset_2]
    assert event_group_name_1 in group_names_asset_2
    assert event_group_name_2 in group_names_asset_2

    # 6. VERIFY OPC UA CONFIGURATION IS PRESERVED AFTER IMPORT
    shown_eg1 = run(
        f"az iot ops ns asset opcua event-group show --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1}"
    )
    config_eg1 = json.loads(shown_eg1["eventGroupConfiguration"])
    assert config_eg1.get("publishingInterval") == publishing_interval_1
    assert config_eg1.get("queueSize") == queue_size_1

    shown_eg2 = run(
        f"az iot ops ns asset opcua event-group show --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_2}"
    )
    config_eg2 = json.loads(shown_eg2["eventGroupConfiguration"])
    assert config_eg2.get("publishingInterval") == publishing_interval_2
    assert config_eg2.get("queueSize") == queue_size_2

    # 7. TEST IMPORT WITH NEW EVENT GROUP (ADD NEW)
    new_event_group_name = f"imported-eg-{generate_random_string(6, force_lower=True)}"
    import_payload = exported_data.copy()
    import_payload.append({
        "name": new_event_group_name,
        "dataSource": "ns=3;i=2000",
        "eventGroupConfiguration": json.dumps({
            "publishingInterval": 750,
            "queueSize": 15
        }),
        "defaultDestinations": []
    })

    import_file_new = f"/tmp/import_opcua_event_groups_new_{generate_random_string(8)}.json"
    tracked_files.append(import_file_new)
    with open(import_file_new, "w") as f:
        json.dump(import_payload, f)

    run(
        f"az iot ops ns asset opcua event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {import_file_new}"
    )

    # Verify new event group was added
    event_groups_after_import = run(
        f"az iot ops ns asset opcua event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    group_names_after_import = [eg["name"] for eg in event_groups_after_import]
    assert new_event_group_name in group_names_after_import

    # 8. TEST REMOVE AND RESTORE CYCLE
    # Re-export to capture current state
    reexport_result = run(
        f"az iot ops ns asset opcua event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format json --od {output_dir} --replace"
    )
    reexport_file_path = reexport_result["file_path"]
    tracked_files.append(reexport_file_path)

    # Remove the first event group
    run(
        f"az iot ops ns asset opcua event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1}"
    )

    # Verify removal
    event_groups_after_remove = run(
        f"az iot ops ns asset opcua event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    group_names_after_remove = [eg["name"] for eg in event_groups_after_remove]
    assert event_group_name_1 not in group_names_after_remove

    # Import to restore
    run(
        f"az iot ops ns asset opcua event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {reexport_file_path}"
    )

    # Verify restored
    event_groups_after_restore = run(
        f"az iot ops ns asset opcua event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    group_names_after_restore = [eg["name"] for eg in event_groups_after_restore]
    assert event_group_name_1 in group_names_after_restore

    # 9. TEST IMPORT VALIDATION (FAILURE) - Invalid configuration
    import_file_invalid = f"/tmp/import_opcua_event_groups_invalid_{generate_random_string(8)}.json"
    tracked_files.append(import_file_invalid)

    invalid_payload = [{
        "name": "invalid_eg",
        "dataSource": "ns=2;i=9999",
        "eventGroupConfiguration": "{ this is not valid json }"
    }]

    with open(import_file_invalid, "w") as f:
        json.dump(invalid_payload, f)

    # Expect failure
    run(
        f"az iot ops ns asset opcua event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {import_file_invalid}",
        expect_failure=True
    )


def test_namespace_onvif_event_import_export_operations(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """Test ONVIF event-group import and export operations.

    Note: ONVIF supports event-group export/import but does NOT support individual
    event export/import (unlike custom and opcua asset types).
    """
    import os
    import json

    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"onvif-{generate_random_string(8)}"
    asset_name = f"onvif-{generate_random_string(8, force_lower=True)}"
    asset_name_2 = f"onvif-2-{generate_random_string(8, force_lower=True)}"
    event_group_name_1 = f"eg1-{generate_random_string(6, force_lower=True)}"
    event_group_name_2 = f"eg2-{generate_random_string(6, force_lower=True)}"

    # Create Device
    result = run(
        f"az iot ops ns device create --name {device_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    tracked_resources.append(result["id"])

    # Create ONVIF device endpoint
    run(
        f"az iot ops ns device endpoint inbound add onvif --name {endpoint_name} "
        f"--instance {instance_name} -g {resource_group} --device {device_name} "
        f"--endpoint-address 'http://192.168.1.100:8080/onvif/device'"
    )

    # Create ONVIF asset 1
    asset_1 = run(
        f"az iot ops ns asset onvif create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"ONVIF Device for Event Export/Import Testing\""
    )
    tracked_resources.append(asset_1["id"])

    # 1. CREATE EVENT GROUPS
    # ONVIF event groups use data sources like motion detection, video analytics, etc.
    data_source_1 = "motion.detection"
    event_destinations_1 = "topic=factory/onvif/motion qos=Qos1 retain=Never ttl=1800"

    run(
        f"az iot ops ns asset onvif event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1} --data-source {data_source_1} "
        f"--destination {event_destinations_1}"
    )

    data_source_2 = "video.analytics"
    event_destinations_2 = "topic=factory/onvif/analytics qos=Qos0 retain=Keep ttl=3600"

    run(
        f"az iot ops ns asset onvif event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_2} --data-source {data_source_2} "
        f"--destination {event_destinations_2}"
    )

    # 2. EXPORT EVENT GROUPS
    output_dir = "/tmp"
    export_result = run(
        f"az iot ops ns asset onvif event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format json --od {output_dir} --replace"
    )

    assert "file_path" in export_result
    export_file_path = export_result["file_path"]
    tracked_files.append(export_file_path)

    # Verify the exported file exists and contains the event groups
    assert os.path.exists(export_file_path)
    with open(export_file_path, "r") as f:
        exported_data = json.load(f)

    assert len(exported_data) == 2
    exported_group_names = [eg["name"] for eg in exported_data]
    assert event_group_name_1 in exported_group_names
    assert event_group_name_2 in exported_group_names

    # 3. VERIFY DATA SOURCE IS PRESERVED IN EXPORT
    for eg in exported_data:
        if eg["name"] == event_group_name_1:
            assert eg["dataSource"] == data_source_1
        elif eg["name"] == event_group_name_2:
            assert eg["dataSource"] == data_source_2

    # 4. CREATE SECOND ONVIF ASSET FOR CROSS-ASSET IMPORT TEST
    asset_2 = run(
        f"az iot ops ns asset onvif create --name {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"ONVIF Device 2 for Import Testing\""
    )
    tracked_resources.append(asset_2["id"])

    # 5. IMPORT EVENT GROUPS TO SECOND ASSET
    run(
        f"az iot ops ns asset onvif event-group import --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --if {export_file_path}"
    )

    # Verify event groups are imported to second asset
    event_groups_asset_2 = run(
        f"az iot ops ns asset onvif event-group list --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group}"
    )

    group_names_asset_2 = [eg["name"] for eg in event_groups_asset_2]
    assert event_group_name_1 in group_names_asset_2
    assert event_group_name_2 in group_names_asset_2

    # 6. VERIFY DATA SOURCE IS PRESERVED AFTER IMPORT
    shown_eg1 = run(
        f"az iot ops ns asset onvif event-group show --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1}"
    )
    assert shown_eg1["dataSource"] == data_source_1

    shown_eg2 = run(
        f"az iot ops ns asset onvif event-group show --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_2}"
    )
    assert shown_eg2["dataSource"] == data_source_2

    # 7. TEST IMPORT WITH NEW EVENT GROUP (ADD NEW)
    new_event_group_name = f"imported-eg-{generate_random_string(6, force_lower=True)}"
    import_payload = exported_data.copy()
    import_payload.append({
        "name": new_event_group_name,
        "dataSource": "ptz.control",
        "eventGroupConfiguration": "{}",
        "defaultDestinations": []
    })

    import_file_new = f"/tmp/import_onvif_event_groups_new_{generate_random_string(8)}.json"
    tracked_files.append(import_file_new)
    with open(import_file_new, "w") as f:
        json.dump(import_payload, f)

    run(
        f"az iot ops ns asset onvif event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {import_file_new}"
    )

    # Verify new event group was added
    event_groups_after_import = run(
        f"az iot ops ns asset onvif event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    group_names_after_import = [eg["name"] for eg in event_groups_after_import]
    assert new_event_group_name in group_names_after_import

    # 8. TEST REMOVE AND RESTORE CYCLE
    # Re-export to capture current state
    reexport_result = run(
        f"az iot ops ns asset onvif event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format json --od {output_dir} --replace"
    )
    reexport_file_path = reexport_result["file_path"]
    tracked_files.append(reexport_file_path)

    # Remove the first event group
    run(
        f"az iot ops ns asset onvif event-group remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1}"
    )

    # Verify removal
    event_groups_after_remove = run(
        f"az iot ops ns asset onvif event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    group_names_after_remove = [eg["name"] for eg in event_groups_after_remove]
    assert event_group_name_1 not in group_names_after_remove

    # Import to restore
    run(
        f"az iot ops ns asset onvif event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {reexport_file_path}"
    )

    # Verify restored
    event_groups_after_restore = run(
        f"az iot ops ns asset onvif event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    group_names_after_restore = [eg["name"] for eg in event_groups_after_restore]
    assert event_group_name_1 in group_names_after_restore

    # 9. TEST IMPORT VALIDATION (FAILURE) - Invalid configuration
    import_file_invalid = f"/tmp/import_onvif_event_groups_invalid_{generate_random_string(8)}.json"
    tracked_files.append(import_file_invalid)

    invalid_payload = [{
        "name": "invalid_eg",
        "dataSource": "motion/invalid",
        "eventGroupConfiguration": "{ this is not valid json }"
    }]

    with open(import_file_invalid, "w") as f:
        json.dump(invalid_payload, f)

    # Expect failure
    run(
        f"az iot ops ns asset onvif event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {import_file_invalid}",
        expect_failure=True
    )


def test_namespace_asset_event_eventgroup_formats_import_export(
    require_init, tracked_resources: List[str], tracked_files: List[str]
):
    """Test event-group and event import/export operations with different file formats.

    This test verifies that export and import work correctly with:
    - JSON format
    - YAML format

    Note: CSV format is technically supported for individual event export/import,
    but not for event-group export/import. CSV tests are omitted due to known
    issues with custom configuration handling in CSV export.

    It also tests cross-format compatibility (export in one format, import from another).
    """
    import os
    import json
    import yaml

    # Setup test variables
    instance_name = require_init["instanceName"]
    resource_group = require_init["resourceGroup"]
    device_name = f"dev-{generate_random_string(8, force_lower=True)}"
    endpoint_name = f"custom-{generate_random_string(8)}"
    asset_name = f"custom-{generate_random_string(8, force_lower=True)}"
    asset_name_2 = f"custom-2-{generate_random_string(8, force_lower=True)}"
    event_group_name_1 = f"eg1-{generate_random_string(6, force_lower=True)}"
    event_group_name_2 = f"eg2-{generate_random_string(6, force_lower=True)}"
    event_name_1 = f"ev1-{generate_random_string(6, force_lower=True)}"
    event_name_2 = f"ev2-{generate_random_string(6, force_lower=True)}"

    output_dir = "/tmp"

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

    # Create Custom asset 1
    asset_1 = run(
        f"az iot ops ns asset custom create --name {asset_name} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"Custom Device for Format Testing\""
    )
    tracked_resources.append(asset_1["id"])

    # Create Custom asset 2 for cross-asset import tests
    asset_2 = run(
        f"az iot ops ns asset custom create --name {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --device {device_name} --endpoint {endpoint_name} "
        f"--description \"Custom Device 2 for Format Testing\""
    )
    tracked_resources.append(asset_2["id"])

    # 1. CREATE EVENT GROUPS WITH EVENTS
    custom_config_path, _ = create_config_file(tracked_files)
    event_dest_1 = "topic=factory/eg1 qos=Qos1 retain=Never ttl=3600"
    event_dest_2 = "topic=factory/eg2 qos=Qos0 retain=Keep ttl=1800"

    run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1} --data-source event.source.1 "
        f"--config {custom_config_path} --destination {event_dest_1}"
    )

    run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_2} --data-source event.source.2 "
        f"--config {custom_config_path} --destination {event_dest_2}"
    )

    # Add events to first event group
    run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --name {event_name_1} "
        f"--data-source event.data.1 --config {custom_config_path}"
    )
    run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --name {event_name_2} "
        f"--data-source event.data.2 --config {custom_config_path}"
    )

    # ==================== PART 1: JSON FORMAT TESTS ====================

    # 2. EXPORT EVENT GROUPS IN JSON FORMAT
    json_export_result = run(
        f"az iot ops ns asset custom event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format json --od {output_dir} --replace"
    )

    assert "file_path" in json_export_result
    json_export_file = json_export_result["file_path"]
    tracked_files.append(json_export_file)

    # Verify JSON file exists and is valid
    assert os.path.exists(json_export_file)
    assert json_export_file.endswith(".json")
    with open(json_export_file, "r") as f:
        json_data = json.load(f)

    assert len(json_data) == 2
    json_group_names = [eg["name"] for eg in json_data]
    assert event_group_name_1 in json_group_names
    assert event_group_name_2 in json_group_names

    # 3. EXPORT EVENTS IN JSON FORMAT
    json_events_export_result = run(
        f"az iot ops ns asset custom event export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --format json --od {output_dir} --replace"
    )

    assert "file_path" in json_events_export_result
    json_events_file = json_events_export_result["file_path"]
    tracked_files.append(json_events_file)

    # Verify JSON events file
    assert os.path.exists(json_events_file)
    assert json_events_file.endswith(".json")
    with open(json_events_file, "r") as f:
        json_events_data = json.load(f)

    assert len(json_events_data) == 2
    json_event_names = [ev["name"] for ev in json_events_data]
    assert event_name_1 in json_event_names
    assert event_name_2 in json_event_names

    # ==================== PART 2: YAML FORMAT TESTS ====================

    # 4. EXPORT EVENT GROUPS IN YAML FORMAT
    yaml_export_result = run(
        f"az iot ops ns asset custom event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format yaml --od {output_dir} --replace"
    )

    assert "file_path" in yaml_export_result
    yaml_export_file = yaml_export_result["file_path"]
    tracked_files.append(yaml_export_file)

    # Verify YAML file exists and is valid
    assert os.path.exists(yaml_export_file)
    assert yaml_export_file.endswith(".yaml")
    with open(yaml_export_file, "r") as f:
        yaml_data = yaml.safe_load(f)

    assert len(yaml_data) == 2
    yaml_group_names = [eg["name"] for eg in yaml_data]
    assert event_group_name_1 in yaml_group_names
    assert event_group_name_2 in yaml_group_names

    # 5. EXPORT EVENTS IN YAML FORMAT
    yaml_events_export_result = run(
        f"az iot ops ns asset custom event export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --format yaml --od {output_dir} --replace"
    )

    assert "file_path" in yaml_events_export_result
    yaml_events_file = yaml_events_export_result["file_path"]
    tracked_files.append(yaml_events_file)

    # Verify YAML events file
    assert os.path.exists(yaml_events_file)
    assert yaml_events_file.endswith(".yaml")
    with open(yaml_events_file, "r") as f:
        yaml_events_data = yaml.safe_load(f)

    assert len(yaml_events_data) == 2
    yaml_event_names = [ev["name"] for ev in yaml_events_data]
    assert event_name_1 in yaml_event_names
    assert event_name_2 in yaml_event_names

    # ==================== PART 3: CROSS-FORMAT IMPORT TESTS ====================

    # 6. IMPORT EVENT GROUPS FROM JSON TO SECOND ASSET
    run(
        f"az iot ops ns asset custom event-group import --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --if {json_export_file}"
    )

    # Verify import from JSON
    event_groups_from_json = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group}"
    )
    json_imported_names = [eg["name"] for eg in event_groups_from_json]
    assert event_group_name_1 in json_imported_names
    assert event_group_name_2 in json_imported_names

    # 9. IMPORT EVENTS FROM JSON TO SECOND ASSET'S EVENT GROUP
    run(
        f"az iot ops ns asset custom event import --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --if {json_events_file}"
    )

    # Verify events imported from JSON
    events_from_json = run(
        f"az iot ops ns asset custom event list --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1}"
    )
    json_imported_event_names = [ev["name"] for ev in events_from_json]
    assert event_name_1 in json_imported_event_names
    assert event_name_2 in json_imported_event_names

    # 10. REMOVE EVENT GROUPS FROM SECOND ASSET FOR YAML IMPORT TEST
    run(
        f"az iot ops ns asset custom event-group remove --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1}"
    )
    run(
        f"az iot ops ns asset custom event-group remove --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_2}"
    )

    # 11. IMPORT EVENT GROUPS FROM YAML
    run(
        f"az iot ops ns asset custom event-group import --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --if {yaml_export_file}"
    )

    # Verify import from YAML
    event_groups_from_yaml = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group}"
    )
    yaml_imported_names = [eg["name"] for eg in event_groups_from_yaml]
    assert event_group_name_1 in yaml_imported_names
    assert event_group_name_2 in yaml_imported_names

    # 12. IMPORT EVENTS FROM YAML
    run(
        f"az iot ops ns asset custom event import --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --if {yaml_events_file}"
    )

    # Verify events imported from YAML
    events_from_yaml = run(
        f"az iot ops ns asset custom event list --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1}"
    )
    yaml_imported_event_names = [ev["name"] for ev in events_from_yaml]
    assert event_name_1 in yaml_imported_event_names
    assert event_name_2 in yaml_imported_event_names

    # ==================== PART 4: DATA PRESERVATION TESTS ====================

    # 11. VERIFY DATA SOURCE IS PRESERVED ACROSS FORMATS
    # Check event group data source in second asset after YAML import
    shown_eg1 = run(
        f"az iot ops ns asset custom event-group show --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_1}"
    )
    assert shown_eg1["dataSource"] == "event.source.1"

    shown_eg2 = run(
        f"az iot ops ns asset custom event-group show --asset {asset_name_2} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name_2}"
    )
    assert shown_eg2["dataSource"] == "event.source.2"

    # ==================== PART 5: MANUAL FILE CREATION AND IMPORT ====================

    # 12. CREATE AND IMPORT A MANUALLY CREATED JSON FILE
    manual_eg_name = f"manual-eg-{generate_random_string(6, force_lower=True)}"
    manual_json_file = f"/tmp/manual_event_group_{generate_random_string(8)}.json"
    tracked_files.append(manual_json_file)

    manual_json_data = [{
        "name": manual_eg_name,
        "dataSource": "manual.data.source",
        "eventGroupConfiguration": "{}",
        "defaultDestinations": []
    }]
    with open(manual_json_file, "w") as f:
        json.dump(manual_json_data, f)

    run(
        f"az iot ops ns asset custom event-group import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --if {manual_json_file}"
    )

    # Verify manual JSON import
    event_groups_after_manual = run(
        f"az iot ops ns asset custom event-group list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group}"
    )
    manual_imported_names = [eg["name"] for eg in event_groups_after_manual]
    assert manual_eg_name in manual_imported_names

    # 13. CREATE AND IMPORT A MANUALLY CREATED YAML FILE (for events)
    manual_ev_name = f"manual-ev-{generate_random_string(6, force_lower=True)}"
    manual_yaml_file = f"/tmp/manual_event_{generate_random_string(8)}.yaml"
    tracked_files.append(manual_yaml_file)

    manual_yaml_data = [{
        "name": manual_ev_name,
        "dataSource": "manual.event.source",
        "eventConfiguration": "{}"
    }]
    with open(manual_yaml_file, "w") as f:
        yaml.dump(manual_yaml_data, f)

    run(
        f"az iot ops ns asset custom event import --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1} --if {manual_yaml_file}"
    )

    # Verify manual YAML import
    events_after_manual = run(
        f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name_1}"
    )
    manual_event_names = [ev["name"] for ev in events_after_manual]
    assert manual_ev_name in manual_event_names

    # ==================== PART 6: REPLACE FLAG TESTS ====================

    # 14. TEST EXPORT WITH --replace FLAG (OVERWRITE EXISTING FILE)
    # Export again with replace flag - should overwrite the existing file
    replace_export_result = run(
        f"az iot ops ns asset custom event-group export --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --format json --od {output_dir} --replace"
    )

    assert "file_path" in replace_export_result
    replace_export_file = replace_export_result["file_path"]

    # File should exist and be valid
    assert os.path.exists(replace_export_file)
    with open(replace_export_file, "r") as f:
        replace_data = json.load(f)

    # Should now have all event groups including the manually added one
    replace_group_names = [eg["name"] for eg in replace_data]
    assert event_group_name_1 in replace_group_names
    assert event_group_name_2 in replace_group_names
    assert manual_eg_name in replace_group_names
