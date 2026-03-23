# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List
import pytest

from ...generators import generate_random_string
from ...helpers import run, wait_for_expected_count
from .namespace_helpers import create_config_file, assert_point_properties, assert_event_properties


pytestmark = [pytest.mark.rpsaas, pytest.mark.long_running]


def test_namespace_custom_asset_event_lifecycle_operations(
    asset_factory, tracked_files: List[str]
):
    """Test complete lifecycle of custom asset event-group and datapoint operations."""
    # Setup from shared fixtures
    info = asset_factory("custom")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    event_group_name = f"event-group-{generate_random_string(6, force_lower=True)}"
    datapoint_name_1 = f"dp1-{generate_random_string(6, force_lower=True)}"
    datapoint_name_2 = f"dp2-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE EVENT GROUP
    custom_config_path, custom_config = create_config_file(tracked_files)
    event_destinations = "topic=factory/custom/events qos=Qos1 retain=Never ttl=3600"

    event_result = run(
        f"az iot ops ns asset custom event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} "
        f"--config {custom_config_path} --destination {event_destinations}"
    )

    assert_event_properties(
        event_result,
        name=event_group_name,
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
    custom_config_path, custom_config = create_config_file(tracked_files)

    datapoint_result = run(
        f"az iot ops ns asset custom event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {datapoint_name_1} "
        f"--config {custom_config_path}"
    )

    assert_point_properties(
        datapoint_result,
        name=datapoint_name_1,
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
    datapoints_list = wait_for_expected_count(
        list_cmd=(
            f"az iot ops ns asset custom event list --asset {asset_name} --instance {instance_name} "
            f"-g {resource_group} --event-group {event_group_name}"
        ),
        expected_count=2,
        expected_names=[datapoint_name_1, datapoint_name_2],
    )

    assert len(datapoints_list) >= 2

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


def test_namespace_opcua_asset_event_lifecycle_operations(asset_factory):
    """Test complete lifecycle of OPC UA asset event-group operations (events only)."""
    # Setup from shared fixtures
    info = asset_factory("opcua")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    event_group_name = f"event-group-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE EVENT WITH FULL OPCUA CONFIGURATION
    event_destinations = "topic=factory/opcua/events qos=Qos0 retain=Keep ttl=7200"
    publishing_interval = 500
    queue_size = 10
    start_instance = "ns=3;i=3001"

    event_result = run(
        f"az iot ops ns asset opcua event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} "
        f"--destination {event_destinations} --publish-int {publishing_interval} "
        f"--queue-size {queue_size} --start-inst \"{start_instance}\""
    )

    assert_event_properties(
        event_result,
        name=event_group_name,
        opcua_configuration={"startInstance": start_instance},
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


def test_namespace_onvif_asset_event_lifecycle_operations(asset_factory):
    """Test complete lifecycle of ONVIF asset event-group operations (events only)."""
    # Setup from shared fixtures
    info = asset_factory("onvif")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    event_group_name = f"event-group-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE EVENT GROUP
    event_destinations = "topic=factory/onvif/events qos=Qos1 retain=Never ttl=1800"

    event_result = run(
        f"az iot ops ns asset onvif event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} "
        f"--destination {event_destinations}"
    )

    assert_event_properties(
        event_result,
        name=event_group_name,
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

    # 5b. ADD EVENT to the event group
    event_name = f"event-{generate_random_string(6, force_lower=True)}"
    event_result = run(
        f"az iot ops ns asset onvif event add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {event_name}"
    )
    assert isinstance(event_result, list)
    assert any(ev["name"] == event_name for ev in event_result)

    # 5c. LIST EVENTS
    events_list = run(
        f"az iot ops ns asset onvif event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name}"
    )
    assert any(ev["name"] == event_name for ev in events_list)

    # 5d. REMOVE EVENT
    run(
        f"az iot ops ns asset onvif event remove --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name} --name {event_name}"
    )
    remaining_events = run(
        f"az iot ops ns asset onvif event list --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --event-group {event_group_name}"
    )
    assert not any(ev["name"] == event_name for ev in remaining_events)

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


def test_namespace_sse_asset_event_lifecycle_operations(asset_factory):
    """Test complete lifecycle of SSE asset event-group operations (events only)."""
    # Setup from shared fixtures
    info = asset_factory("sse")
    asset_name = info["name"]
    instance_name = info["instanceName"]
    resource_group = info["resourceGroup"]
    event_group_name = f"event-group-{generate_random_string(6, force_lower=True)}"

    # 1. CREATE EVENT GROUP
    event_destinations = "topic=factory/sse/events qos=Qos1 retain=Never ttl=1800"

    event_result = run(
        f"az iot ops ns asset sse event-group add --asset {asset_name} --instance {instance_name} "
        f"-g {resource_group} --name {event_group_name} "
        f"--destination {event_destinations}"
    )

    assert_event_properties(
        event_result,
        name=event_group_name,
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
        f"--destination {event_destinations}"
    )

    assert_point_properties(
        datapoint_result,
        name=datapoint_name_1,
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
