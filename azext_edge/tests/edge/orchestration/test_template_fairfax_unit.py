# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Generated FF source artifacts and cloud-specific deployment selection."""

import json

import pytest
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.providers.orchestration.runtime_profiles import (
    RuntimeChannel, RuntimeIdentity, resolve_runtime_identity, validate_upgrade_boundary,
)
from azext_edge.edge.providers.orchestration.targets import InitTargets, InstancePhase
from azext_edge.edge.providers.orchestration.template import TemplateBlueprint
from azext_edge.edge.providers.orchestration.template_fairfax import (
    TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX,
    TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX,
)

from .test_deployment_policy_unit import FF_CONFIGURATION, FF_FOUNDATION
from .test_template_unit import EXPECTED_INSTANCE_RESOURCE_KEYS


@pytest.mark.parametrize("blueprint", [
    TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX, TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX,
])
def test_ff_uses_existing_blueprint_format_without_gds_or_loaded_blobs(blueprint):
    assert isinstance(blueprint, TemplateBlueprint)
    content = json.dumps(blueprint.content).lower()
    assert "gds" not in content
    assert "$fxv" not in content
    assert blueprint.content["metadata"]["_generator"]["version"] == "0.48.1.52935"


def test_ff_enablement_has_source_dependency_targets_and_preserves_install_conditions():
    content = TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX.content
    assert content["variables"]["VERSIONS"] == {
        moniker: target["version"] for moniker, target in FF_FOUNDATION.items()
    }
    assert content["variables"]["TRAINS"] == {
        moniker: target["train"] for moniker, target in FF_FOUNDATION.items()
    }
    resources = content["resources"]
    assert set(resources) == {"cluster", "certManagerExtension", "secretStoreExtension"}
    assert resources["certManagerExtension"]["condition"] == "[equals(parameters('trustConfig').source, 'SelfSigned')]"
    for key in ("certManagerExtension", "secretStoreExtension"):
        assert resources[key]["properties"]["autoUpgradeMinorVersion"] is False


def test_ff_instance_preserves_source_contract():
    content = TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX.content
    assert set(content["resources"]) == set(EXPECTED_INSTANCE_RESOURCE_KEYS)
    assert content["parameters"]["clusterLocation"]["allowedValues"] == ["usgovvirginia"]
    assert "defaultValue" not in content["parameters"]["clusterLocation"]
    assert content["variables"]["VERSIONS"] == {"iotOperations": "1.5.44", "connectors": "1.5.21"}
    assert content["variables"]["TRAINS"] == {"iotOperations": "stable"}
    assert FF_CONFIGURATION.items() <= content["variables"]["defaultAioConfigurationSettings"].items()
    assert content["resources"]["aioExtension"]["properties"]["autoUpgradeMinorVersion"] is False
    resources = [
        resource for resource in content["resources"].values()
        if resource["type"].startswith("Microsoft.IoTOperations/")
    ]
    assert {resource["apiVersion"] for resource in resources} == {"2026-10-01"}


@pytest.mark.parametrize("phase", [None, InstancePhase.EXT, InstancePhase.INSTANCE, InstancePhase.RESOURCES])
def test_ff_selects_complete_cloud_blueprint_in_every_deployment_phase(phase):
    public = get_runtime_catalog().get(RuntimeChannel.STABLE)
    original = public.copy_instance_blueprint().content
    profile = get_runtime_catalog("AzureUSGovernment").for_create()
    targets = InitTargets(
        "cluster", "rg", cloud_name="AzureUSGovernment", runtime_profile=profile, location="usgovvirginia",
    )
    template, _ = targets.get_ops_instance_template(phase=phase)
    assert template["variables"]["VERSIONS"]["iotOperations"] == profile.identity.version
    assert template["variables"]["TRAINS"]["iotOperations"] == profile.identity.train
    assert template["variables"]["VERSIONS"]["connectors"] == "1.5.21"
    assert FF_CONFIGURATION.items() <= template["variables"]["defaultAioConfigurationSettings"].items()
    if phase in (None, InstancePhase.EXT):
        assert template["resources"]["aioExtension"]["properties"]["version"] == "[variables('resolvedVersion')]"
    assert template["parameters"]["aioExtensionVersion"]["defaultValue"] == ""
    assert template["variables"]["resolvedVersion"] == (
        TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX.content["variables"]["resolvedVersion"]
    )
    assert public.copy_instance_blueprint().content == original


def test_ff_artifact_mapping_does_not_enable_public_preview_or_leak_into_public_catalog():
    catalog = get_runtime_catalog("AzureUSGovernment")
    profile = catalog.for_create()
    assert profile.cloud_name == "AzureUSGovernment"
    assert profile.identity.channel == RuntimeChannel.STABLE
    assert (profile.identity.version, profile.identity.train) == ("1.5.44", "stable")
    assert profile.source_ref == "releases/v1.5.x/2610-ff"
    assert profile.source_commit == "56d1f14b761f3af61804c7f602796f4d555a956f"
    assert profile.require_opcua_connector_version() == "1.5.21"
    assert profile.iotops_api_version == "2026-10-01"
    assert catalog.for_upgrade(profile.identity) is profile
    assert resolve_runtime_identity(
        profile.identity.version, profile.identity.train, catalog.qualification_identities,
    ) == profile.identity
    assert resolve_runtime_identity(
        profile.identity.version, profile.identity.train, get_runtime_catalog().qualification_identities,
    ).cloud_name == "AzureCloud"
    with pytest.raises(ValidationError, match="No reviewed preview"):
        catalog.for_create(use_preview=True)
    assert profile.identity not in get_runtime_catalog().qualification_identities


@pytest.mark.parametrize("overrides", [{"version": "1.5.43"}, {"train": "preview"}])
def test_ff_rejects_unreviewed_artifact_overrides(overrides):
    profile = get_runtime_catalog("AzureUSGovernment").for_create()
    with pytest.raises(ValidationError):
        profile.validate_overrides(**overrides)
    with pytest.raises(ValidationError):
        InitTargets(
            "cluster", "rg", cloud_name="AzureUSGovernment",
            ops_version=overrides.get("version"), ops_train=overrides.get("train"),
        )


def test_upgrade_cannot_cross_cloud_identity_boundary():
    ff = get_runtime_catalog("AzureUSGovernment").for_create().identity
    public = RuntimeIdentity(RuntimeChannel.STABLE, ff.version, ff.train)
    with pytest.raises(ValidationError, match="Cannot upgrade"):
        validate_upgrade_boundary(public, ff)


def test_full_ff_generation_preserves_additional_parameters_resources_and_enablement_settings(mocker):
    from azext_edge.edge.providers.orchestration import deployment_policy, runtime_catalog

    instance = TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX.copy()
    instance.parameters["futureSetting"] = {"type": "string", "defaultValue": "source-default"}
    instance.content["resources"]["futureResource"] = {
        "type": "Microsoft.Example/widgets", "apiVersion": "2026-01-01", "name": "source-resource",
    }
    enablement = TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX.copy()
    enablement.content["resources"]["certManagerExtension"]["properties"]["configurationSettings"]["future"] = "keep"
    mocker.patch.object(runtime_catalog, "TEMPLATE_BLUEPRINT_INSTANCE_FAIRFAX", instance)
    mocker.patch.object(deployment_policy, "TEMPLATE_BLUEPRINT_ENABLEMENT_FAIRFAX", enablement)
    targets = InitTargets("cluster", "rg", cloud_name="AzureUSGovernment")
    template, _ = targets.get_ops_instance_template()
    foundation, _ = targets.get_ops_enablement_template()
    assert template["parameters"]["futureSetting"] == instance.parameters["futureSetting"]
    assert template["resources"]["futureResource"] == instance.content["resources"]["futureResource"]
    assert foundation["resources"]["certManagerExtension"]["properties"]["configurationSettings"]["future"] == "keep"
    template["parameters"]["futureSetting"]["defaultValue"] = "modified"
    assert instance.parameters["futureSetting"]["defaultValue"] == "source-default"
