# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import pytest

from azure.cli.core.azclierror import RequiredArgumentMissingError
from azext_edge.edge.commands_assets import (
    add_asset_event,
    export_asset_events,
    import_asset_events,
    list_asset_events,
    remove_asset_event
)
from azext_edge.edge.common import FileType
from azext_edge.edge.providers.rpsaas.adr.base import ADR_API_VERSION

from .conftest import (
    MINIMUM_ASSET,
    FULL_ASSET
)
from .....generators import generate_random_string


FULL_EVENT = FULL_ASSET["properties"]["events"][0]


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": MINIMUM_ASSET,
        "resources.begin_create_or_update_by_id": {
            "properties": {"events": {"result": generate_random_string()}}
        }
    },
    {
        "resources.get": FULL_ASSET,
        "resources.begin_create_or_update_by_id": {
            "properties": {"events": {"result": generate_random_string()}}
        }
    },
], ids=["minimal", "full"], indirect=True)
@pytest.mark.parametrize("capability_id", [None, generate_random_string()])
@pytest.mark.parametrize("name", [None, generate_random_string()])
@pytest.mark.parametrize("observability_mode", [None, generate_random_string()])
@pytest.mark.parametrize("queue_size", [None, 20])
@pytest.mark.parametrize("sampling_interval", [None, 33])
def test_add_asset_event(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    capability_id,
    name,
    observability_mode,
    queue_size,
    sampling_interval,
):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    event_notifier = generate_random_string()
    result_events = add_asset_event(
        cmd=mocked_cmd,
        asset_name=asset_name,
        event_notifier=event_notifier,
        capability_id=capability_id,
        name=name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        resource_group_name=resource_group_name
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    original_asset = mocked_resource_management_client.resources.get.return_value.original
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    expected_asset = poller.result()
    assert result_events == expected_asset["properties"]["events"]

    # Asset changes
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_asset["id"]
    assert call_kwargs["api_version"] == ADR_API_VERSION

    # Check update request
    request_events = call_kwargs["parameters"]["properties"]["events"]

    assert request_events[:-1] == original_asset["properties"].get("events", [])
    added_event = request_events[-1]
    assert added_event["capabilityId"] == (capability_id or name)
    assert added_event["name"] == name
    assert added_event["observabilityMode"] == observability_mode

    assert added_event["eventNotifier"] == event_notifier
    assert added_event["eventConfiguration"]
    assert "dataSource" not in added_event
    custom_configuration = json.loads(added_event["eventConfiguration"])
    assert custom_configuration.get("samplingInterval") == (
        sampling_interval if event_notifier else None
    )
    assert custom_configuration.get("queueSize") == (queue_size if event_notifier else None)


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": MINIMUM_ASSET},
    {"resources.get": FULL_ASSET},
], ids=["minimal", "full"], indirect=True)
@pytest.mark.parametrize("extension", FileType.list())
@pytest.mark.parametrize("output_dir", [None, generate_random_string()])
@pytest.mark.parametrize("replace", [False, True])
def test_export_asset_events(
    mocked_cmd,
    asset_helpers_fixture,
    mocked_resource_management_client,
    mocked_dump_content_to_file,
    extension,
    output_dir,
    replace
):
    patched_to_csv = asset_helpers_fixture["convert_sub_points_to_csv"]
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    result = export_asset_events(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        extension=extension,
        output_dir=output_dir,
        replace=replace
    )
    assert result["file_path"] == mocked_dump_content_to_file.return_value
    mocked_resource_management_client.resources.get.assert_called_once()
    original_asset = mocked_resource_management_client.resources.get.return_value.as_dict.return_value
    events = original_asset["properties"].get("events", [])
    default_config = original_asset["properties"].get("defaultEventsConfiguration", "{}")
    expected_fieldnames = None
    if extension in [FileType.csv.value, FileType.portal_csv.value]:
        expected_fieldnames = patched_to_csv.return_value
        call_kwargs = patched_to_csv.call_args.kwargs
        assert call_kwargs["sub_points"] == events
        assert call_kwargs["sub_point_type"] == "events"
        assert call_kwargs["default_configuration"] == default_config
        assert call_kwargs["portal_friendly"] == (extension == FileType.portal_csv.value)

    call_kwargs = mocked_dump_content_to_file.call_args.kwargs
    assert call_kwargs["content"] == events
    assert call_kwargs["file_name"] == f"{asset_name}_events"
    assert call_kwargs["extension"] == extension.replace("-", ".")
    assert call_kwargs["fieldnames"] == expected_fieldnames
    assert call_kwargs["output_dir"] == output_dir
    assert call_kwargs["replace"] == replace


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": MINIMUM_ASSET,
        "resources.begin_create_or_update_by_id": {
            "properties": {"events": {"result": generate_random_string()}}
        }
    },
    {
        "resources.get": FULL_ASSET,
        "resources.begin_create_or_update_by_id": {
            "properties": {"events": {"result": generate_random_string()}}
        }
    },
], ids=["minimal", "full"], indirect=True)
@pytest.mark.parametrize("mocked_read_file_content_as_dict", [[
    FULL_ASSET["properties"]["events"][0],
    {
        "capabilityId": generate_random_string(),
        "eventConfiguration": "{\"samplingInterval\": 100}",
        "eventNotifier": FULL_ASSET["properties"]["events"][1]["eventNotifier"],
        "name": generate_random_string()
    }
]], ids=["events"], indirect=True)
@pytest.mark.parametrize("replace", [False, True])
def test_import_events(
    mocked_cmd,
    asset_helpers_fixture,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    mocked_read_file_content_as_dict,
    replace
):
    patched_from_csv = asset_helpers_fixture["convert_sub_points_from_csv"]
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    file_path = generate_random_string()
    result = import_asset_events(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        file_path=file_path,
        replace=replace
    )

    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    result_points = poller.result()["properties"]["events"]
    assert result == result_points

    original_asset = mocked_resource_management_client.resources.get.return_value.original
    original_points = original_asset["properties"].get("events", [])

    mocked_read_file_content_as_dict.assert_called_once_with(file_path=file_path)
    file_points = mocked_read_file_content_as_dict.return_value

    patched_from_csv.assert_called_once_with(file_points)

    # make sure that file points won't update full asset points
    expected_points = file_points if replace or not original_points else original_points
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_asset["id"]
    assert call_kwargs["api_version"] == ADR_API_VERSION
    assert call_kwargs["parameters"]["properties"]["events"] == expected_points


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.get": MINIMUM_ASSET},
    {"resources.get": FULL_ASSET},
], ids=["minimal", "full"], indirect=True)
def test_list_asset_events(mocked_cmd, mocked_resource_management_client):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    result_events = list_asset_events(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    original_asset = mocked_resource_management_client.resources.get.return_value.as_dict.return_value
    assert result_events == original_asset["properties"].get("events", [])


@pytest.mark.parametrize("mocked_resource_management_client", [
    {
        "resources.get": FULL_ASSET,
        "resources.begin_create_or_update_by_id": {
            "properties": {"events": {"result": generate_random_string()}}
        }
    },
], ids=["full"], indirect=True)
@pytest.mark.parametrize("event_notifier, name", [
    (FULL_EVENT["eventNotifier"], FULL_EVENT["name"]),
    (FULL_EVENT["eventNotifier"], None),
    (None, FULL_EVENT["name"]),
    (generate_random_string(), generate_random_string()),
    (generate_random_string(), None),
    (None, generate_random_string()),
])
def test_remove_asset_event(
    mocked_cmd,
    mock_check_cluster_connectivity,
    mocked_resource_management_client,
    event_notifier,
    name
):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    result_events = remove_asset_event(
        cmd=mocked_cmd,
        asset_name=asset_name,
        event_notifier=event_notifier,
        name=name,
        resource_group_name=resource_group_name
    )
    mocked_resource_management_client.resources.get.assert_called_once()
    mocked_resource_management_client.resources.begin_create_or_update_by_id.assert_called_once()
    original_asset = mocked_resource_management_client.resources.get.return_value.original
    poller = mocked_resource_management_client.resources.begin_create_or_update_by_id.return_value
    expected_asset = poller.result()
    assert result_events == expected_asset["properties"]["events"]

    # Asset changes
    call_kwargs = mocked_resource_management_client.resources.begin_create_or_update_by_id.call_args.kwargs
    assert call_kwargs["resource_id"] == original_asset["id"]
    assert call_kwargs["api_version"] == ADR_API_VERSION

    # Check update request
    request_events = call_kwargs["parameters"]["properties"]["events"]
    original_events = original_asset["properties"]["events"]

    if event_notifier == FULL_EVENT["eventNotifier"] or name == FULL_EVENT["name"]:
        assert len(request_events) + 1 == len(original_events)
        assert request_events == original_events[1:]
    else:
        assert request_events == original_events


def test_remove_asset_event_error(mocked_cmd):
    with pytest.raises(RequiredArgumentMissingError) as e:
        remove_asset_event(
            cmd=mocked_cmd,
            asset_name=generate_random_string(),
            resource_group_name=generate_random_string()
        )
    assert e.value.error_msg == "Provide either the event notifier via --event-notifier or name via "\
        "--event-name to identify the event to remove."
