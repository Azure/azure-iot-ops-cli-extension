# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.providers.orchestration.runtime_profiles import (
    RuntimeChannel,
    RuntimeIdentity,
    RuntimeProfile,
    RuntimeProfileCatalog,
    resolve_runtime_identity,
    validate_upgrade_boundary,
)
from azext_edge.edge.providers.orchestration.targets import InitTargets, merge_template_object
from azext_edge.edge.providers.orchestration.template import (
    TEMPLATE_BLUEPRINT_ENABLEMENT,
    TEMPLATE_BLUEPRINT_INSTANCE,
)


def make_profile(channel, version, train=None, **kwargs):
    # Synthetic fixtures, not generated release inputs or production defaults.
    blueprint = TEMPLATE_BLUEPRINT_INSTANCE.copy()
    blueprint.content["variables"]["VERSIONS"]["iotOperations"] = version
    blueprint.content["variables"]["TRAINS"]["iotOperations"] = train or channel.value
    return RuntimeProfile(channel, "test-release", "test-ref", "test-commit", blueprint, **kwargs)


@pytest.fixture
def profiles():
    return (
        make_profile(RuntimeChannel.STABLE, "1.5.7"),
        make_profile(RuntimeChannel.PREVIEW, "1.6.0-preview.4"),
    )


def test_catalog_defaults_and_upgrade_selection(profiles):
    stable, preview = profiles
    catalog = RuntimeProfileCatalog(profiles)
    assert catalog.for_create() is stable
    assert catalog.for_create(use_preview=True) is preview
    assert catalog.for_upgrade(RuntimeIdentity(RuntimeChannel.STABLE, "1.4.100", "stable")) is stable
    assert catalog.for_upgrade(RuntimeIdentity(RuntimeChannel.PREVIEW, "1.6.0-preview.2", "preview")) is preview


def test_catalog_missing_and_duplicate_profiles_fail(profiles):
    with pytest.raises(ValidationError, match="No reviewed preview"):
        RuntimeProfileCatalog(profiles[:1]).for_create(use_preview=True)
    with pytest.raises(ValidationError, match="Multiple target profiles"):
        RuntimeProfileCatalog([profiles[0], profiles[0]])


@pytest.mark.parametrize("train", ["integration", "canary", "", None])
def test_unmapped_nonpublic_train_is_not_preview(train):
    with pytest.raises(ValidationError):
        resolve_runtime_identity("1.6.0-preview.4", train)


def test_integration_requires_exact_mapping():
    stable = RuntimeIdentity(RuntimeChannel.STABLE, "1.5.7", "integration")
    preview = RuntimeIdentity(RuntimeChannel.PREVIEW, "1.6.0-preview.4", "integration")
    identities = [stable, preview]
    assert resolve_runtime_identity(stable.version, "Integration", identities) == stable
    assert resolve_runtime_identity(preview.version, "integration", identities) == preview
    with pytest.raises(ValidationError, match="no supported runtime profile"):
        resolve_runtime_identity("1.6.0-preview.5", "integration", identities)
    with pytest.raises(ValidationError, match="must remain"):
        validate_upgrade_boundary(stable, preview)


@pytest.mark.parametrize(
    "channel,version,train",
    [
        (RuntimeChannel.STABLE, "1.6.0-preview.4", "stable"),
        (RuntimeChannel.STABLE, "1.5.7", "preview"),
        (RuntimeChannel.PREVIEW, "1.6.0", "preview"),
        (RuntimeChannel.PREVIEW, "1.6.1-preview.4", "preview"),
        (RuntimeChannel.PREVIEW, "1.6.0-preview.0", "preview"),
        (RuntimeChannel.PREVIEW, "1.6.0-rc.4", "preview"),
        (RuntimeChannel.STABLE, "invalid", "stable"),
        (RuntimeChannel.STABLE, None, "stable"),
    ],
)
def test_inconsistent_identity_rejected(channel, version, train):
    with pytest.raises(ValidationError):
        RuntimeIdentity(channel, version, train)


@pytest.mark.parametrize("reverse", [False, True])
def test_cross_profile_upgrade_boundary(profiles, reverse):
    identities = [profile.identity for profile in profiles]
    if reverse:
        identities.reverse()
    with pytest.raises(ValidationError, match="must remain"):
        validate_upgrade_boundary(*identities)


def test_numeric_preview_order_and_downgrade():
    older = RuntimeIdentity(RuntimeChannel.PREVIEW, "1.6.0-preview.2", "preview")
    newer = RuntimeIdentity(RuntimeChannel.PREVIEW, "1.6.0-preview.10", "preview")
    validate_upgrade_boundary(older, newer)
    validate_upgrade_boundary(older, older)
    with pytest.raises(ValidationError, match="downgrade"):
        validate_upgrade_boundary(newer, older)


def test_profile_owns_blueprint_copies():
    blueprint = TEMPLATE_BLUEPRINT_INSTANCE.copy()
    original = deepcopy(blueprint.content)
    profile = RuntimeProfile(RuntimeChannel.STABLE, "test", "branch", "commit", blueprint)
    blueprint.content["variables"].clear()
    returned = profile.copy_instance_blueprint()
    returned.content["resources"].clear()
    assert profile.copy_instance_blueprint().content == original
    with pytest.raises(FrozenInstanceError):
        profile.release = "other"


def test_profile_requires_provenance():
    with pytest.raises(ValidationError, match="resolved source commit"):
        RuntimeProfile(RuntimeChannel.STABLE, "test", "branch", "", TEMPLATE_BLUEPRINT_INSTANCE)


def test_profile_overrides_cannot_change_channel_or_train(profiles):
    stable, preview = profiles
    for profile, kwargs in [
        (stable, {"train": "preview"}),
        (stable, {"version": "1.6.0-preview.4"}),
        (preview, {"version": "1.6.0"}),
        (preview, {"train": "integration"}),
    ]:
        with pytest.raises(ValidationError):
            profile.validate_overrides(**kwargs)
    stable.validate_overrides(version="1.5.8", train="Stable")
    preview.validate_overrides(version="1.6.0-preview.5")
    qualification = make_profile(RuntimeChannel.PREVIEW, "1.6.0-preview.4", "integration")
    with pytest.raises(ValidationError, match="reviewed profile inputs"):
        qualification.validate_overrides(version="1.6.0-preview.5")


def test_targets_use_selected_profile_without_changing_foundation(profiles):
    original_instance = deepcopy(TEMPLATE_BLUEPRINT_INSTANCE.content)
    original_enablement = deepcopy(TEMPLATE_BLUEPRINT_ENABLEMENT.content)
    legacy = InitTargets("cluster", "rg")
    stable_targets = InitTargets("cluster", "rg", runtime_profile=profiles[0], instance_name="custom")
    preview_targets = InitTargets("cluster", "rg", runtime_profile=profiles[1], instance_name="custom")
    assert stable_targets.get_extension_versions(False)["iotOperations"] == {
        "version": "1.5.7", "train": "stable"
    }
    assert preview_targets.get_extension_versions(False)["iotOperations"] == {
        "version": "1.6.0-preview.4", "train": "preview"
    }
    assert legacy.get_ops_enablement_template() == stable_targets.get_ops_enablement_template()
    assert legacy.get_ops_enablement_template() == preview_targets.get_ops_enablement_template()
    for targets in (stable_targets, preview_targets):
        template, _ = targets.get_ops_instance_template()
        assert template["resources"]["aioInstance"]["name"] == "custom"
        assert template["resources"]["broker"]["name"] == "custom/default"
        template["variables"]["VERSIONS"].clear()
        assert targets.get_extension_versions(False)["iotOperations"]["version"]
    assert TEMPLATE_BLUEPRINT_INSTANCE.content == original_instance
    assert TEMPLATE_BLUEPRINT_ENABLEMENT.content == original_enablement


def test_targets_reject_conflicting_overrides(profiles):
    with pytest.raises(ValidationError):
        InitTargets("cluster", "rg", runtime_profile=profiles[0], ops_train="preview")


def test_targets_preserve_additional_instance_properties(profiles):
    blueprint = profiles[1].copy_instance_blueprint()
    blueprint.content["resources"]["aioInstance"]["properties"]["additionalProperty"] = {"mode": "keep"}
    profile = RuntimeProfile(RuntimeChannel.PREVIEW, "test", "branch", "commit", blueprint)
    targets = InitTargets("cluster", "rg", runtime_profile=profile, instance_description="description")
    template, _ = targets.get_ops_instance_template()
    properties = template["resources"]["aioInstance"]["properties"]
    assert properties["additionalProperty"] == {"mode": "keep"}
    assert properties["description"] == "description"
    properties["additionalProperty"]["mode"] = "changed"
    assert profile.copy_instance_blueprint().content == blueprint.content


def test_generated_instance_defaults_and_new_child_names_are_preserved(profiles):
    blueprint = profiles[1].copy_instance_blueprint()
    original_properties = deepcopy(blueprint.content["resources"]["aioInstance"]["properties"])
    child = {"type": "Microsoft.IoTOperations/instances/testResources",
             "name": "[format('{0}/extra', parameters('aioInstanceName'))]"}
    blueprint.content["resources"]["newChild"] = child
    profile = RuntimeProfile(RuntimeChannel.PREVIEW, "test", "branch", "commit", blueprint)
    targets = InitTargets("cluster", "rg", runtime_profile=profile, instance_name="My_Instance")
    for phase in (None, 1, 2, 3):
        template, parameters = targets.get_ops_instance_template(phase=phase)
        assert parameters["aioInstanceName"] == {"value": "my-instance"}
        assert "features" not in parameters
        if phase in (None, 2):
            assert template["resources"]["aioInstance"]["properties"] == original_properties
        if phase in (None, 3):
            assert template["resources"]["newChild"] == child
    assert profile.copy_instance_blueprint().content == blueprint.content


@pytest.mark.parametrize("parameter_defaults", [True, False])
def test_explicit_features_merge_nested_generated_defaults(profiles, parameter_defaults):
    blueprint = profiles[1].copy_instance_blueprint()
    defaults = {"opcua": {"mode": "Stable", "settings": {"retained": "value", "changed": "old"}},
                "otherComponent": {"mode": "Preview"}}
    if parameter_defaults:
        blueprint.content["parameters"]["features"]["defaultValue"] = defaults
    else:
        del blueprint.content["parameters"]["features"]
        blueprint.content["resources"]["aioInstance"]["properties"]["features"] = defaults
    profile = RuntimeProfile(RuntimeChannel.PREVIEW, "test", "branch", "commit", blueprint)
    targets = InitTargets("cluster", "rg", runtime_profile=profile,
                          instance_features=["opcua.mode=Preview"], instance_description="")
    template, parameters = targets.get_ops_instance_template()
    properties = template["resources"]["aioInstance"]["properties"]
    actual = parameters["features"]["value"] if parameter_defaults else properties["features"]
    assert actual == {"opcua": {"mode": "Preview", "settings": {"retained": "value", "changed": "old"}},
                      "otherComponent": {"mode": "Preview"}}
    assert properties["description"] == ""
    if parameter_defaults:
        assert properties["features"] == "[variables('effectiveFeatures')]"
    actual["opcua"]["settings"].clear()
    assert profile.copy_instance_blueprint().content == blueprint.content


@pytest.mark.parametrize("parameter_defaults", [True, False])
def test_feature_expression_merge_stays_in_template_scope(profiles, parameter_defaults):
    blueprint = profiles[1].copy_instance_blueprint()
    if parameter_defaults:
        blueprint.content["parameters"]["featureDefaults"] = {"type": "object", "defaultValue": {}}
        blueprint.content["parameters"]["features"]["defaultValue"] = "[parameters('featureDefaults')]"
    else:
        del blueprint.content["parameters"]["features"]
    profile = RuntimeProfile(RuntimeChannel.PREVIEW, "test", "branch", "commit", blueprint)
    targets = InitTargets("cluster", "rg", runtime_profile=profile,
                          instance_features=["opcua.mode=Preview"])
    template, parameters = targets.get_ops_instance_template()
    assert "features" not in parameters
    expression = (template["parameters"]["features"]["defaultValue"] if parameter_defaults
                  else template["resources"]["aioInstance"]["properties"]["features"])
    source = "parameters('featureDefaults')" if parameter_defaults else "variables('effectiveFeatures')"
    assert expression == (
        "[union(coalesce(" + source + ", createObject()), "
        "json('{\"opcua\":{\"mode\":\"Preview\"}}'))]"
    )
    assert profile.copy_instance_blueprint().content == blueprint.content


def test_object_overlay_merges_nested_settings_and_escapes_arm_literals():
    defaults = {"component": {"mode": "Stable", "settings": {"a": "Enabled", "b": "Disabled"}}}
    override = {"component": {"settings": {"b": "Enabled"}}}
    assert merge_template_object(defaults, override) == {
        "component": {"mode": "Stable", "settings": {"a": "Enabled", "b": "Enabled"}},
    }
    assert defaults["component"]["settings"]["b"] == "Disabled"
    assert merge_template_object("[variables('defaults')]", {"value": "it's"}) == (
        "[union(coalesce(variables('defaults'), createObject()), json('{\"value\":\"it''s\"}'))]"
    )


@pytest.mark.parametrize("bound,limit,value,valid", [
    ("minValue", 3, 3, True), ("minValue", 3, 2, False),
    ("maxValue", 4, 4, True), ("maxValue", 4, 5, False),
])
def test_selected_broker_schema_can_have_one_bound(profiles, bound, limit, value, valid):
    from azure.cli.core.azclierror import InvalidArgumentValueError

    blueprint = profiles[1].copy_instance_blueprint()
    definition = blueprint.content["definitions"]["_1.BrokerConfig"]["properties"]["frontendWorkers"]
    definition.pop("minValue", None)
    definition.pop("maxValue", None)
    definition[bound] = limit
    profile = RuntimeProfile(RuntimeChannel.PREVIEW, "test", "branch", "commit", blueprint)
    if valid:
        targets = InitTargets("cluster", "rg", runtime_profile=profile, broker_frontend_workers=value)
        assert targets.broker_config["frontendWorkers"] == value
    else:
        with pytest.raises(InvalidArgumentValueError, match="frontendWorkers"):
            InitTargets("cluster", "rg", runtime_profile=profile, broker_frontend_workers=value)
    assert profile.copy_instance_blueprint().content == blueprint.content


def test_selected_broker_schema_is_used_and_not_mutated(profiles):
    from azure.cli.core.azclierror import InvalidArgumentValueError

    blueprint = profiles[1].copy_instance_blueprint()
    definition = blueprint.content["definitions"]["_1.BrokerConfig"]["properties"]
    definition["frontendWorkers"]["maxValue"] = 3
    profile = RuntimeProfile(RuntimeChannel.PREVIEW, "test", "branch", "commit", blueprint)
    with pytest.raises(InvalidArgumentValueError, match="frontendWorkers"):
        InitTargets("cluster", "rg", runtime_profile=profile, broker_frontend_workers=4)
    targets = InitTargets("cluster", "rg", runtime_profile=profile, broker_frontend_workers=3)
    assert targets.get_broker_config_target_map()["frontendWorkers"] == 3
    assert profile.copy_instance_blueprint().content == blueprint.content
