# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Checks for the generated internal-qualification artifact, not live compatibility."""

import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import call

import pytest
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.providers.orchestration.preview import confirm_preview_creation
from azext_edge.edge.providers.orchestration.runtime_catalog import (
    PREVIEW_AGREEMENT_URL,
    PREVIEW_NOTICE,
    PREVIEW_PROFILE,
    get_runtime_catalog,
)
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel, RuntimeProfile
from azext_edge.edge.providers.orchestration.targets import InitTargets, InstancePhase
from azext_edge.edge.providers.orchestration.template import (
    TEMPLATE_BLUEPRINT_ENABLEMENT,
    TEMPLATE_BLUEPRINT_INSTANCE,
)
from azext_edge.edge.providers.orchestration.template_preview import TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW


EXPECTED_PREVIEW_RESOURCE_KEYS = frozenset({
    "cluster", "aioExtension", "customLocation", "aioInstance", "broker", "brokerAuthn", "brokerListener",
    "dataflowProfile", "dataflowEndpoint", "artifactRegistryEndpoint", "opcUaConnectorTemplate", "mcpDefaultPolicy",
    "mcpAioConnection",
})
EXTENSION_KEYS = {"cluster", "aioExtension"}
INSTANCE_KEYS = EXTENSION_KEYS | {"customLocation", "aioInstance"}


@pytest.fixture
def qualification_profile():
    # Exercise the actual generated artifact without registering it for CLI operations.
    return RuntimeProfile(
        channel=RuntimeChannel.PREVIEW,
        release="prev2610",
        source_ref="1.6.0-preview.22",
        source_commit="test-commit",
        instance_blueprint=TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW,
    )


def test_preview_source_identity_and_contract(qualification_profile):
    blueprint = TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW
    content = blueprint.content
    assert blueprint.commit_id == "1dfac78ed54a68cd5458c8d6311ada02514428e3"
    assert content
    assert content["variables"]["VERSIONS"] == {"iotOperations": "1.6.0-preview.22", "connectors": "1.5.12"}
    assert content["variables"]["TRAINS"] == {"iotOperations": "integration"}
    assert qualification_profile.identity.train == "integration"
    assert qualification_profile.identity.channel == RuntimeChannel.PREVIEW
    assert set(content["resources"]) == EXPECTED_PREVIEW_RESOURCE_KEYS
    aio_resources = [r for r in content["resources"].values() if r["type"].startswith("Microsoft.IoTOperations/")]
    assert len(aio_resources) == 10
    assert {r["apiVersion"] for r in aio_resources} == {"2026-09-01-preview"}
    assert content["resources"]["aioExtension"]["properties"]["autoUpgradeMinorVersion"] is False
    assert "disableOpcUaFeature" not in content["parameters"]
    assert content["definitions"]["_1.InstanceFeature"]["properties"]["settings"]["nullable"] is True


def test_preview_keeps_approved_scalars_without_loaded_source_blob():
    content = TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content
    serialized = json.dumps(content)
    assert "$fxv" not in serialized
    assert "AIO_EXTENSION_VALUES" not in serialized
    assert content["variables"]["OPCUA_CONNECTOR_VERSION"] == (
        "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'connectors'), 'version'), "
        "variables('VERSIONS').connectors)]"
    )
    assert content["definitions"]["_1.AdvancedConfig"]["properties"]["connectors"]["properties"]["version"] == {
        "type": "string", "nullable": True,
    }
    for variable, key, value in (
        ("CONNECTORS_CHART_REGISTRY", "registry", "aioconnectorsdev.azurecr.io"),
        ("CONNECTORS_CHART_REPOSITORY", "repository", "aio-connectors/helmchart/microsoft-aio-connectors"),
        ("CONNECTORS_IMAGE_REGISTRY", "imageRegistry", "aioconnectorsdev.azurecr.io"),
    ):
        assert content["variables"][variable] == (
            "[coalesce(tryGet(tryGet(parameters('advancedConfig'), 'connectors'), '"
            + key + "'), '" + value + "')]"
        )
        assert content["definitions"]["_1.AdvancedConfig"]["properties"]["connectors"]["properties"][key] == {
            "type": "string", "nullable": True,
        }
    config = content["variables"]["defaultAioConfigurationSettings"]
    assert config["connectors.image.tag"] == "[variables('OPCUA_CONNECTOR_VERSION')]"
    assert config["connectors.image.registry"] == "[variables('CONNECTORS_CHART_REGISTRY')]"
    assert config["connectors.image.repository"] == "[variables('CONNECTORS_CHART_REPOSITORY')]"
    assert config["connectors.values.image.registry"] == "[variables('CONNECTORS_IMAGE_REGISTRY')]"
    assert content["parameters"]["enableGdsManager"] == {"type": "bool", "defaultValue": True}
    assert config["connectors.values.gdsManager.enabled"] == "[if(parameters('enableGdsManager'), 'true', 'false')]"


def test_preview_persistence_sku_and_endpoint_defaults():
    content = TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content
    assert content["parameters"]["enablePersistence"] == {"type": "bool", "defaultValue": True}
    helper = content["functions"][0]["members"]["buildBrokerPersistence"]
    assert helper["parameters"] == [
        {"type": "bool", "name": "enablePersistence"},
        {"$ref": "#/definitions/_1.BrokerPersistence", "nullable": True, "name": "persistence"},
    ]
    assert helper["output"]["value"] == (
        "[if(not(parameters('enablePersistence')), null(), coalesce(parameters('persistence'), "
        "createObject('maxSize', '3Gi', 'retain', createObject('mode', 'None'), "
        "'subscriberQueue', createObject('mode', 'None'), 'stateStore', createObject('mode', 'Custom', "
        "'stateStoreSettings', createObject('dynamic', createObject('mode', 'Enabled'))))))]"
    )
    assert content["variables"]["BROKER_CONFIG"]["persistence"] == (
        "[_2.buildBrokerPersistence(parameters('enablePersistence'), "
        "tryGet(parameters('brokerConfig'), 'persistence'))]"
    )
    assert content["parameters"]["sku"] == {
        "type": "string", "allowedValues": ["Essentials", "Standard"], "nullable": True,
    }
    assert content["resources"]["aioInstance"]["sku"] == (
        "[if(not(equals(parameters('sku'), null())), createObject('name', parameters('sku')), null())]"
    )
    assert content["resources"]["opcUaConnectorTemplate"]["properties"]["deviceInboundEndpointTypes"] == [
        {"endpointType": "Microsoft.OpcUa"}, {"endpointType": "Microsoft.OpcUa.WoT"},
    ]


@pytest.mark.parametrize("phase", [None, InstancePhase.EXT, InstancePhase.INSTANCE, InstancePhase.RESOURCES])
def test_preview_phase_resources_and_defaults(qualification_profile, phase):
    source = TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content
    targets = InitTargets("cluster", "rg", runtime_profile=qualification_profile, instance_name="My_Instance")
    template, parameters = targets.get_ops_instance_template(phase=phase)
    resources = template["resources"]
    expected = (EXTENSION_KEYS if phase == InstancePhase.EXT else
                INSTANCE_KEYS if phase == InstancePhase.INSTANCE else EXPECTED_PREVIEW_RESOURCE_KEYS)
    assert set(resources) == expected
    assert parameters["aioInstanceName"] == {"value": "my-instance"}
    assert "enableGdsManager" not in parameters
    assert "enablePersistence" not in parameters
    assert "sku" not in parameters
    assert "features" not in parameters
    assert template["parameters"]["enableGdsManager"]["defaultValue"] is True
    assert template["parameters"]["enablePersistence"]["defaultValue"] is True
    assert template["variables"]["defaultAioConfigurationSettings"] == source["variables"][
        "defaultAioConfigurationSettings"
    ]
    if phase in (InstancePhase.INSTANCE, InstancePhase.RESOURCES):
        existing = EXTENSION_KEYS | {"customLocation"}
        if phase == InstancePhase.RESOURCES:
            existing.add("aioInstance")
        assert all(resources[key]["existing"] for key in existing)
    if phase in (None, InstancePhase.INSTANCE):
        assert resources["aioInstance"]["properties"] == {
            **source["resources"]["aioInstance"]["properties"], "description": None,
        }
    if phase in (None, InstancePhase.RESOURCES):
        for resource in resources.values():
            if resource["type"].startswith("Microsoft.IoTOperations/instances/"):
                assert resource["name"].startswith("my-instance/")
        assert resources["opcUaConnectorTemplate"]["condition"] == source["resources"]["opcUaConnectorTemplate"][
            "condition"
        ]
        assert resources["mcpDefaultPolicy"]["name"] == "my-instance/aio-mcp-policy-v1"
        assert resources["mcpAioConnection"]["name"] == "my-instance/aio"
        assert resources["mcpAioConnection"]["properties"]["service"]["name"] == "my-instance-mcp"


@pytest.mark.parametrize("instance_name", [None, "My_Instance"])
def test_preview_mcp_policy_preserves_source_contract(qualification_profile, instance_name):
    source = deepcopy(TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content["resources"]["mcpDefaultPolicy"])
    template, parameters = InitTargets(
        "cluster", "rg", runtime_profile=qualification_profile, instance_name=instance_name,
    ).get_ops_instance_template()
    policy = template["resources"]["mcpDefaultPolicy"]
    assert "features" not in parameters
    assert policy["type"] == "Microsoft.IoTOperations/instances/mcpAuthorizationPolicies"
    assert policy["condition"] == "[equals(tryGet(tryGet(parameters('features'), 'mcp'), 'mode'), 'Preview')]"
    if instance_name:
        source["name"] = "my-instance/aio-mcp-policy-v1"
    assert policy == source


@pytest.mark.parametrize("instance_name", [None, "My_Instance", "a" * 32, "a" * 33])
def test_preview_mcp_connection_preserves_source_contract(qualification_profile, instance_name):
    source = deepcopy(TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content["resources"]["mcpAioConnection"])
    targets = InitTargets("cluster", "rg", runtime_profile=qualification_profile, instance_name=instance_name)
    template, parameters = targets.get_ops_instance_template()
    connection = template["resources"]["mcpAioConnection"]
    assert "features" not in parameters
    assert connection["condition"] == (
        "[and(equals(tryGet(tryGet(parameters('features'), 'mcp'), 'mode'), 'Preview'), "
        "lessOrEquals(length(coalesce(parameters('aioInstanceName'), format('aio-{0}', variables('HASH')))), 32))]"
    )
    assert connection["type"] == "Microsoft.IoTOperations/instances/mcpServerConnections"
    assert connection["dependsOn"] == ["aioInstance", "customLocation", "mcpDefaultPolicy"]
    assert connection["properties"]["authorization"] == {
        "mode": "PolicyBased", "policyRef": {"name": "aio-mcp-policy-v1"},
    }
    assert connection["properties"]["trustBundle"] == "/var/run/certs"
    assert connection["properties"]["service"]["path"] == "/mcp"
    if instance_name:
        assert parameters["aioInstanceName"] == {"value": targets.instance_name}
        source["name"] = f"{targets.instance_name}/aio"
        source["properties"]["service"]["name"] = f"{targets.instance_name}-mcp"
    assert connection == source


def test_preview_extension_versions_exclude_connector_metadata(qualification_profile):
    targets = InitTargets("cluster", "rg", runtime_profile=qualification_profile)
    assert targets.get_extension_versions(False) == {
        "iotOperations": {"version": "1.6.0-preview.22", "train": "integration"},
    }


@pytest.mark.parametrize("mode", ["Preview", "Disabled"])
def test_preview_mcp_feature_is_not_exposed_by_cli(qualification_profile, mode):
    from azure.cli.core.azclierror import InvalidArgumentValueError

    with pytest.raises(InvalidArgumentValueError, match="Supported feature keys: opcua.mode"):
        InitTargets("cluster", "rg", runtime_profile=qualification_profile, instance_features=[f"mcp.mode={mode}"])


@pytest.mark.parametrize("mode", ["Stable", "Preview", "Disabled"])
def test_preview_features_use_source_contract(qualification_profile, mode):
    template, parameters = InitTargets(
        "cluster", "rg", runtime_profile=qualification_profile, instance_features=[f"opcua.mode={mode}"]
    ).get_ops_instance_template()
    assert parameters["features"] == {"value": {"opcua": {"mode": mode, "settings": {}}}}
    assert template["resources"]["aioInstance"]["properties"]["features"] == "[parameters('features')]"
    assert ("opcUaConnectorTemplate" in template["resources"]) == (mode != "Disabled")
    assert "effectiveFeatures" not in template["variables"]
    assert template["variables"]["TRAINS"]["iotOperations"] == "integration"


def test_preview_explicit_configuration_overlays_preserve_other_defaults(qualification_profile):
    source = TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content
    template, _ = InitTargets(
        "cluster", "rg", runtime_profile=qualification_profile,
        ops_config=["connectors.values.gdsManager.enabled=false", "connectors.image.registry=qualification.example"],
    ).get_ops_instance_template()
    expected = deepcopy(source["variables"]["defaultAioConfigurationSettings"])
    expected.update({"connectors.values.gdsManager.enabled": "false",
                     "connectors.image.registry": "qualification.example"})
    assert template["variables"]["defaultAioConfigurationSettings"] == expected
    assert source["variables"]["defaultAioConfigurationSettings"]["connectors.image.registry"] == (
        "[variables('CONNECTORS_CHART_REGISTRY')]"
    )


@pytest.mark.parametrize("preview_first", [False, True])
def test_preview_preparation_isolated_from_ga_and_shared_foundation(qualification_profile, preview_first):
    blueprints = (TEMPLATE_BLUEPRINT_INSTANCE, TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW, TEMPLATE_BLUEPRINT_ENABLEMENT)
    snapshots = [deepcopy(blueprint.content) for blueprint in blueprints]
    stable = get_runtime_catalog().for_create()
    order = [stable, qualification_profile]
    if preview_first:
        order.reverse()
    foundation = InitTargets("cluster", "rg").get_ops_enablement_template()
    for profile in order:
        targets = InitTargets("cluster", "rg", runtime_profile=profile)
        assert targets.get_ops_enablement_template() == foundation
        assert targets.get_extension_versions(False)["iotOperations"] == {
            "version": profile.identity.version, "train": profile.identity.train,
        }
        template, _ = targets.get_ops_instance_template()
        assert template["variables"]["defaultAioConfigurationSettings"] == profile.copy_instance_blueprint().content[
            "variables"
        ]["defaultAioConfigurationSettings"]
        template["variables"].clear()
        template["resources"].clear()
        profile.copy_instance_blueprint().content["definitions"].clear()
    assert [blueprint.content for blueprint in blueprints] == snapshots


@pytest.mark.parametrize("confirm_yes", [False, True])
def test_preview_agreement_url_does_not_bypass_missing_notice(qualification_profile, confirm_yes):
    assert PREVIEW_AGREEMENT_URL == "https://azure.microsoft.com/en-us/support/legal/preview-supplemental-terms/"
    draft = replace(
        qualification_profile,
        instance_blueprint=qualification_profile.copy_instance_blueprint(),
        preview_agreement_url=PREVIEW_AGREEMENT_URL,
        preview_notice=None,
    )
    with pytest.raises(ValidationError, match="approved notice"):
        confirm_preview_creation(draft, confirm_yes=confirm_yes)


def test_bundled_preview_registered_without_changing_default_or_train():
    from azext_edge.edge.providers.orchestration.runtime_profiles import resolve_runtime_identity

    catalog = get_runtime_catalog()
    assert catalog.for_create().channel == RuntimeChannel.STABLE
    profile = catalog.for_create(use_preview=True)
    assert profile is PREVIEW_PROFILE
    assert profile.copy_instance_blueprint() == TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW
    assert profile.identity.version == "1.6.0-preview.22"
    assert profile.identity.train == "integration"
    assert profile.source_ref == "1.6.0-preview.22"
    assert profile.source_commit == "5e54c8e8679c8e41a3e08a5e25583d1e185981b5"
    assert resolve_runtime_identity(
        profile.identity.version, profile.identity.train, catalog.qualification_identities
    ) == profile.identity
    assert catalog.for_upgrade(profile.identity) is profile
    assert profile.require_opcua_connector_version() == "1.5.12"
    assert profile.require_opcua_connector_version() == (
        TEMPLATE_BLUEPRINT_INSTANCE_PREVIEW.content["variables"]["VERSIONS"]["connectors"]
    )


@pytest.mark.parametrize("version", [
    "1.6.0-preview.9", "1.6.0-preview.18", "1.6.0-preview.19", "1.6.0-preview.20", "1.6.0-preview.21",
])
def test_unqualified_preview_integration_versions_are_not_retained(version):
    from azext_edge.edge.providers.orchestration.runtime_profiles import resolve_runtime_identity

    with pytest.raises(ValidationError):
        resolve_runtime_identity(version, "integration", get_runtime_catalog().qualification_identities)


@pytest.mark.parametrize("confirm_yes,answer", [(False, False), (False, True), (True, None)])
def test_bundled_preview_normal_consent_flow(mocker, confirm_yes, answer):
    from azext_edge.edge.providers.orchestration import preview

    profile = get_runtime_catalog().for_create(use_preview=True)
    output = mocker.patch.object(preview.console, "print")
    mocker.patch.object(preview.sys.stdin, "isatty", return_value=not confirm_yes)
    ask = mocker.patch.object(preview.Confirm, "ask", return_value=answer)
    assert confirm_preview_creation(profile, confirm_yes=confirm_yes) is (True if confirm_yes else answer)
    assert output.call_args_list == [call(PREVIEW_NOTICE, markup=False), call(PREVIEW_AGREEMENT_URL, markup=False)]
    if confirm_yes:
        ask.assert_not_called()
    else:
        assert ask.call_args.kwargs["default"] is True
