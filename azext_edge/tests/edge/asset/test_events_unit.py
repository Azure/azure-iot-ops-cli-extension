# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
import pytest

from azure.cli.core.azclierror import RequiredArgumentMissingError
from ....edge.commands_assets import (
    add_asset_event,
    list_asset_events,
    remove_asset_event
)
from . import (
    EMBEDDED_CLI_ASSETS_PATH,
    MINIMUM_ASSET,
    FULL_ASSET
)
from ...helpers import parse_rest_command
from ...generators import generate_generic_id


FULL_EVENT = FULL_ASSET["properties"]["events"][0]


@pytest.mark.parametrize("embedded_cli_client", [{
    "path": EMBEDDED_CLI_ASSETS_PATH,
    "as_json_result": {"properties": {"events": {"result": generate_generic_id()}}}
}], indirect=True)
@pytest.mark.parametrize("show_asset_fixture", [MINIMUM_ASSET, FULL_ASSET], indirect=True)
@pytest.mark.parametrize("capability_id", [None, generate_generic_id()])
@pytest.mark.parametrize("name", [None, generate_generic_id()])
@pytest.mark.parametrize("observability_mode", [None, generate_generic_id()])
@pytest.mark.parametrize("queue_size", [None, 20])
@pytest.mark.parametrize("sampling_interval", [None, 33])
@pytest.mark.parametrize("resource_group_name", [None, generate_generic_id()])
def test_add_asset_event(
    fixture_cmd,
    embedded_cli_client,
    show_asset_fixture,
    capability_id,
    name,
    observability_mode,
    queue_size,
    sampling_interval,
    resource_group_name
):
    asset_name = generate_generic_id()
    event_notifier = generate_generic_id()
    result_events = add_asset_event(
        cmd=fixture_cmd,
        asset_name=asset_name,
        event_notifier=event_notifier,
        capability_id=capability_id,
        name=name,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        resource_group_name=resource_group_name
    )
    # Show
    show_asset, original_asset = show_asset_fixture
    assert show_asset.call_args.kwargs.get("resource_group_name") == resource_group_name

    # Asset changes
    assert result_events == next(embedded_cli_client.as_json.side_effect)["properties"]["events"]

    request = embedded_cli_client.invoke.call_args[0][-1]
    request_dict = parse_rest_command(request)
    assert request_dict["method"] == "PUT"
    assert f"{original_asset['id']}?api-version=" in request_dict["uri"]
    request_events = json.loads(request_dict["body"].strip("'"))["properties"]["events"]

    assert request_events[:-1] == original_asset["properties"]["events"]
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


@pytest.mark.parametrize("show_asset_fixture", [MINIMUM_ASSET, FULL_ASSET], indirect=True)
@pytest.mark.parametrize("resource_group_name", [None, generate_generic_id()])
def test_list_asset_events(fixture_cmd, show_asset_fixture, resource_group_name):
    asset_name = generate_generic_id()
    result_obj = list_asset_events(
        cmd=fixture_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )
    # Show
    show_asset, original_asset = show_asset_fixture
    assert show_asset.call_args.kwargs.get("resource_group_name") == resource_group_name

    # Asset list
    assert result_obj == original_asset["properties"]["events"]


@pytest.mark.parametrize("embedded_cli_client", [{
    "path": EMBEDDED_CLI_ASSETS_PATH,
    "as_json_result": {"properties": {"events": {"result": generate_generic_id()}}}
}], indirect=True)
@pytest.mark.parametrize("show_asset_fixture", [FULL_ASSET], indirect=True)
@pytest.mark.parametrize("resource_group_name", [None, generate_generic_id()])
@pytest.mark.parametrize("event_notifier, name", [
    (FULL_EVENT["eventNotifier"], FULL_EVENT["name"]),
    (FULL_EVENT["eventNotifier"], None),
    (None, FULL_EVENT["name"]),
    (generate_generic_id(), generate_generic_id()),
    (generate_generic_id(), None),
    (None, generate_generic_id()),
])
def test_remove_asset_event(
    fixture_cmd, embedded_cli_client, show_asset_fixture, resource_group_name, event_notifier, name
):
    asset_name = generate_generic_id()
    result_obj = remove_asset_event(
        cmd=fixture_cmd,
        asset_name=asset_name,
        event_notifier=event_notifier,
        name=name,
        resource_group_name=resource_group_name
    )
    # show
    show_asset, original_asset = show_asset_fixture
    original_events = original_asset["properties"]["events"]
    assert show_asset.call_args.kwargs.get("resource_group_name") == resource_group_name

    assert result_obj == next(embedded_cli_client.as_json.side_effect)["properties"]["events"]

    # Asset changes
    request = embedded_cli_client.invoke.call_args[0][-1]
    request_body = parse_rest_command(request)["body"]
    request_events = json.loads(request_body.strip("'"))["properties"]["events"]
    if event_notifier == FULL_EVENT["eventNotifier"] or name == FULL_EVENT["name"]:
        assert len(request_events) + 1 == len(original_events)
        assert request_events == original_events[1:]
    else:
        assert request_events == original_events


@pytest.mark.parametrize("resource_group_name", [None, generate_generic_id()])
def test_remove_asset_event_error(fixture_cmd, resource_group_name):
    asset_name = generate_generic_id()
    with pytest.raises(RequiredArgumentMissingError) as e:
        remove_asset_event(
            cmd=fixture_cmd,
            asset_name=asset_name,
            resource_group_name=resource_group_name
        )
    assert e.value.error_msg == "Provide either the event notifier via --event-notifier or name via --name"\
        " to identify the event to remove."
