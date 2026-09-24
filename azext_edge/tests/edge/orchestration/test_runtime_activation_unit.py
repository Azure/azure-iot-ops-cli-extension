# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Exercise lifecycle routing with the real bundled catalog and mocked services."""

import json
from copy import deepcopy
from unittest.mock import call

import pytest
import responses

from azext_edge.edge.commands_edge import create_instance, update_instance, upgrade_instance
from azext_edge.edge.providers.orchestration import preview
from azext_edge.edge.providers.orchestration.common import EXTENSION_TYPE_OPS
from azext_edge.edge.providers.orchestration.resources.connector_templates import ConnectorTemplates
from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel
from azext_edge.edge.providers.orchestration.template_preview import TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW
from azext_edge.edge.providers.orchestration.upgrade2 import UpgradeManager

from .resources.test_instances_unit import get_instance_endpoint, get_mock_instance_record, mock_runtime_discovery
from .test_runtime_commands_unit import create_args, isolated_work as isolated_work_fixture
from .test_upgrade2_unit import UpgradeScenario


isolated_work = isolated_work_fixture


@pytest.mark.parametrize("no_preflight", [False, True])
def test_bundled_preview_create_with_yes_reaches_work(mocker, isolated_work, no_preflight):
    manager, writer = isolated_work
    output = mocker.patch.object(preview.console, "print")
    mocker.patch.object(preview.sys.stdin, "isatty", return_value=False)
    ask = mocker.patch.object(preview.Confirm, "ask")
    profile = get_runtime_catalog().for_create(use_preview=True)

    create_instance(**create_args(), use_preview=True, confirm_yes=True, no_preflight=no_preflight)

    writer.assert_called_once()
    ask.assert_not_called()
    assert manager._targets.runtime_profile is profile
    assert manager._targets.get_extension_versions(False)["iotOperations"] == {
        "version": profile.identity.version, "train": profile.identity.train,
    }
    template, _ = manager._targets.get_ops_instance_template()
    assert template["parameters"]["enableGdsManager"]["defaultValue"] is True
    assert template["variables"]["CONNECTORS_CHART_REGISTRY"] == (
        TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content["variables"]["CONNECTORS_CHART_REGISTRY"]
    )
    assert output.call_args_list == [
        call(profile.preview_notice, markup=False), call(profile.preview_agreement_url, markup=False),
    ]


@pytest.mark.parametrize("answer", [False, True])
def test_bundled_preview_create_respects_interactive_choice(mocker, isolated_work, answer):
    manager, writer = isolated_work
    mocker.patch.object(preview.console, "print")
    mocker.patch.object(preview.sys.stdin, "isatty", return_value=True)
    mocker.patch.object(preview.Confirm, "ask", return_value=answer)
    create_instance(**create_args(), use_preview=True)
    assert writer.call_count == int(answer)
    assert manager._bootstrap_ux.call_count == int(answer)


def test_default_create_still_selects_ga_without_preview_consent(mocker, isolated_work):
    manager, writer = isolated_work
    consent = mocker.patch.object(preview.console, "print")
    create_instance(**create_args())
    writer.assert_called_once()
    consent.assert_not_called()
    assert manager._targets.runtime_profile.channel == RuntimeChannel.STABLE


def test_bundled_preview_update_preserves_payload_and_selects_connector_tag(mocker, mocked_cmd, mocked_responses):
    profile = get_runtime_catalog().for_create(use_preview=True)
    record = get_mock_instance_record("instance", "rg", features={
        "opcua": {"mode": "Disabled", "settings": {"retained": "Enabled"}},
        "otherComponent": {"mode": "Preview"},
    })
    record["properties"]["additionalProperty"] = {"preserved": True}
    original = deepcopy(record)
    endpoint = get_instance_endpoint(resource_group_name="rg", instance_name="instance")
    mocked_responses.add(responses.GET, endpoint, json=record)
    mock_runtime_discovery(mocked_responses, record, profile.identity.version, profile.identity.train)
    mocked_responses.add(responses.PUT, endpoint, json=record)
    mocker.patch.object(ConnectorTemplates, "check_default_opcua_template_needed", return_value=(True, None))
    connector = mocker.patch.object(ConnectorTemplates, "create_default_opcua_template")

    update_instance(
        mocked_cmd, "instance", "rg", instance_features=["opcua.mode=Preview"],
        instance_description="updated description", wait_sec=0,
    )

    writes = [c for c in mocked_responses.calls if c.request.method == "PUT"]
    assert len(writes) == 1
    body = json.loads(writes[0].request.body)
    assert body["properties"]["features"] == {
        "opcua": {"mode": "Preview", "settings": {"retained": "Enabled"}},
        "otherComponent": {"mode": "Preview"},
    }
    assert body["properties"]["additionalProperty"] == {"preserved": True}
    assert body["properties"]["description"] == "updated description"
    assert record == original
    assert connector.call_args.kwargs["connector_version"] == profile.require_opcua_connector_version()


def test_preview_connector_backfill_shape_matches_generated_resource(mocker, mocked_cmd):
    profile = get_runtime_catalog().for_create(use_preview=True)
    connectors = ConnectorTemplates(mocked_cmd)
    extended_location = {"name": "/custom/location", "type": "CustomLocation"}
    mocker.patch.object(connectors.instances, "get_ext_loc", return_value=extended_location)
    writer = mocker.patch.object(connectors.ops, "begin_create_or_update")
    mocker.patch(
        "azext_edge.edge.providers.orchestration.resources.connector_templates.wait_for_terminal_state",
        return_value={},
    )

    connectors.create_default_opcua_template(
        "rg", "instance", connector_version=profile.require_opcua_connector_version(), no_status=True,
    )

    resource = TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content["resources"]["opcUaConnectorTemplate"]
    expected = deepcopy(resource["properties"])
    tag = profile.require_opcua_connector_version()
    expected["connectorMetadataRef"] = f"mcr.microsoft.com/azureiotoperations/aio-connectors/opcua-metadata:{tag}"
    expected["runtimeConfiguration"]["managedConfigurationSettings"]["imageConfigurationSettings"][
        "tagDigestSettings"
    ]["tag"] = tag
    assert writer.call_args.kwargs["resource"] == {"extendedLocation": extended_location, "properties": expected}


@pytest.mark.parametrize("connector_exists", [False, True])
def test_bundled_preview_upgrade_plan_uses_preview_target_and_shared_foundation(
    mocked_cmd, mocked_responses, connector_exists,
):
    profile = get_runtime_catalog().for_create(use_preview=True)
    scenario = UpgradeScenario().set_extension(
        EXTENSION_TYPE_OPS, ext_vers=profile.identity.version, ext_train=profile.identity.train,
    )
    scenario.set_auxiliary_kwargs(opcua_connector_template_exists=connector_exists)
    scenario.set_instance_mock(mocked_responses, "instance", "rg")
    manager = UpgradeManager(mocked_cmd, "rg", "instance", no_progress=True)
    state = manager.analyze_cluster()
    assert manager.runtime_profile is profile
    assert state.connector_template_needed is (not connector_exists)
    if not connector_exists:
        assert state.connector_template_version == profile.require_opcua_connector_version()
    assert manager.targets.get_extension_versions() == scenario.targets.get_extension_versions()
    assert not [c for c in mocked_responses.calls if c.request.method in {"PUT", "PATCH", "DELETE"}]


def test_bundled_preview_upgrade_repairs_same_runtime_without_qualification_block(mocked_cmd, mocked_responses):
    profile = get_runtime_catalog().for_create(use_preview=True)
    scenario = UpgradeScenario().set_extension(
        EXTENSION_TYPE_OPS, ext_vers=profile.identity.version, ext_train=profile.identity.train,
        provisioning_state="Failed",
    )
    scenario.set_instance_mock(mocked_responses, "instance", "rg")
    upgrade_instance(mocked_cmd, "rg", "instance", confirm_yes=True, no_progress=True)
    patches = [c for c in mocked_responses.calls if c.request.method == "PATCH"]
    assert len(patches) == 1
    properties = json.loads(patches[0].request.body)["properties"]
    assert properties["version"] == profile.identity.version
    # Same-train repair does not redundantly patch the unchanged release train.
    assert "releaseTrain" not in properties
