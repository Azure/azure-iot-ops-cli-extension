# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import hashlib
from io import BytesIO
import json
from pathlib import Path
from runpy import run_path
from zipfile import ZipFile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
resolver = run_path(str(ROOT / ".github/actions/build-int-test-matrix/runtime_targets.py"))


def template(version, train="stable"):
    content = {"variables": {"VERSIONS": {"iotOperations": version}, "TRAINS": {"iotOperations": train}}}
    return f"TEMPLATE_BLUEPRINT_INSTANCE = TemplateBlueprint(commit_id='abc', content={content!r})"


@pytest.fixture
def release_index():
    entries, artifacts = [], {}
    for cli_version, runtime in [
        ("2.7.0", "1.3.137"), ("2.8.0", "1.4.41"), ("2.10.0", "1.4.112"),
        ("2.11.0", "1.5.41"), ("2.12.0a1", "1.6.0"),
    ]:
        archive = BytesIO()
        with ZipFile(archive, "w") as wheel:
            wheel.writestr(resolver["TEMPLATE_PATH"], template(runtime))
        url = f"https://example.invalid/azure_iot_ops-{cli_version}-py3-none-any.whl"
        content = archive.getvalue()
        artifacts[url] = content
        entries.append({
            "metadata": {"version": cli_version}, "downloadUrl": url,
            "sha256Digest": hashlib.sha256(content).hexdigest(),
        })
    return entries, artifacts


@pytest.mark.parametrize("generations", [[1], [2], [1, 2]])
def test_discovery_uses_runtime_lines_not_cli_or_patch_subtraction(release_index, generations):
    entries, artifacts = release_index
    result = resolver["resolve_previous"]("1.5.45", generations, entries, fetch=artifacts.__getitem__)
    expected = {"n-1": "1.4.112", "n-2": "1.3.137"}
    assert {key: value["version"] for key, value in result.items()} == {
        f"n-{number}": expected[f"n-{number}"] for number in generations
    }
    for definition in result.values():
        assert definition["train"] == "stable"
        assert definition["create_args"] == ""
        assert hashlib.sha256(artifacts[definition["wheel_url"]]).hexdigest() == definition["sha256"]


def test_discovery_moves_with_candidate_runtime(release_index):
    entries, artifacts = release_index
    result = resolver["resolve_previous"]("1.6.10", [1, 2], entries, fetch=artifacts.__getitem__)
    assert [value["version"] for value in result.values()] == ["1.5.41", "1.4.112"]


def test_missing_previous_generation_is_an_error(release_index):
    entries, artifacts = release_index
    with pytest.raises(ValueError, match="Cannot resolve"):
        resolver["resolve_previous"]("1.4.200", [2], entries, fetch=artifacts.__getitem__)


def test_hash_mismatch_fails_before_reading_template(release_index):
    entries, artifacts = release_index
    entries[-2]["sha256Digest"] = "0" * 64
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        resolver["resolve_previous"]("1.5.45", [1], entries, fetch=artifacts.__getitem__)


def test_template_reader_does_not_execute_code(tmp_path):
    sentinel = tmp_path / "must-not-exist"
    source = f"open({str(sentinel)!r}, 'w').write('unsafe')\n" + template("1.4.112")
    assert resolver["template_identity"](source) == ("1.4.112", "stable")
    assert not sentinel.exists()


@pytest.mark.parametrize("url", [
    "http://example.invalid/a.whl", "https://user@example.invalid/a.whl",
    "https://example.invalid/a.whl?token=value", "https://example.invalid/a.whl#fragment",
])
def test_release_artifact_urls_require_credential_free_https(url):
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        resolver["validate_url"](url)
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        resolver["ReleaseRedirectHandler"]().redirect_request(None, None, 302, "", {}, url)


def test_workflow_selection_inputs_preserve_current_default():
    workflow = yaml.load((ROOT / ".github/workflows/int_test.yml").read_text(), Loader=yaml.BaseLoader)
    for event in ("workflow_call", "workflow_dispatch"):
        inputs = workflow["on"][event]["inputs"]
        for key, default in (("test-current", "true"), ("test-n-1", "false"), ("test-n-2", "false")):
            assert inputs[key]["type"] == "boolean"
            assert inputs[key]["default"] == default
        assert json.loads(inputs["upgrade-baselines"]["default"]) == {}
    action = workflow["jobs"]["build-matrix"]["steps"][-1]
    assert action["with"]["test-current"] == "${{ github.event_name == 'schedule' || inputs.test-current }}"
    assert action["with"]["test-n-1"] == "${{ inputs.test-n-1 || false }}"
    assert action["with"]["test-n-2"] == "${{ inputs.test-n-2 || false }}"


@pytest.mark.parametrize("preserve", [True, False])
def test_baseline_provisioning_preserves_scenario_arguments(mocker, monkeypatch, preserve):
    from azext_edge.tests.edge.init.int import test_init_int as tests

    baseline = {"version": "1.4.112", "train": "stable", "create_args": "--ops-version 1.4.112"}
    monkeypatch.setenv("azext_edge_baseline_extension_dir", "/baseline")
    monkeypatch.setenv("azext_edge_runtime_channel", "stable")
    monkeypatch.setenv("AZURE_EXTENSION_DIR", "/candidate")
    monkeypatch.setenv("azext_edge_preserve_runtime", "true" if preserve else "false")
    mocker.patch.object(tests, "configured_baseline", return_value=baseline)
    command = mocker.patch.object(tests, "run")
    mocker.patch.object(tests, "assert_aio_init")
    verify = mocker.patch.object(tests, "assert_runtime")
    compat = mocker.patch.object(tests, "assert_compat_runtime")
    assertions = [
        mocker.patch.object(tests, name) for name in (
            "assert_aio_instance", "assert_broker_args", "assert_dataflow_profile_args", "assert_trust_config_args",
        )
    ]
    provision = mocker.patch.object(tests.subprocess, "run")
    tests.test_init_scenario({
        "additionalInitArgs": "", "additionalCreateArgs": "--feature opcua.mode=Disabled",
        "clusterName": "cluster", "resourceGroup": "rg", "schemaRegistryId": "/registry",
        "adrNamespaceId": "/namespace", "instanceName": "instance",
        "redeployment": False, "continueOnError": False,
    }, [])
    assert provision.call_count == 1
    arguments = provision.call_args.args[0]
    assert arguments[-4:] == [
        "--ops-version", "1.4.112", "--feature", "opcua.mode=Disabled",
    ]
    assert provision.call_args.kwargs["env"]["AZURE_EXTENSION_DIR"] == "/baseline"
    assert provision.call_args.kwargs["env"]["PYTHONPATH"] == "/baseline/azure-iot-ops"
    assert provision.call_args.kwargs["check"] is True
    command.assert_called_once()
    assert command.call_args.args[0].startswith("az iot ops init ")
    if preserve:
        compat.assert_called_once_with("instance", "rg", "stable", baseline)
        verify.assert_not_called()
    else:
        verify.assert_called_once_with("instance", "rg", "stable", baseline)
        compat.assert_not_called()
    for assertion in assertions:
        assert assertion.call_count == int(preserve)
        if preserve:
            assert assertion.call_args.kwargs["check_defaults"] is False
            assert assertion.call_args.kwargs["feature"] == "opcua.mode=Disabled"


@pytest.mark.parametrize("channel", ["stable", "preview"])
@pytest.mark.parametrize("source_selector", ["", " --use-preview"])
def test_explicit_baseline_provisioning_uses_only_baseline_arguments(mocker, monkeypatch, channel, source_selector):
    import shlex

    from azext_edge.tests.edge.init.int import test_init_int as tests

    builder = run_path(str(ROOT / ".github/actions/build-int-test-matrix/build_matrix.py"))
    baseline = {
        "wheel_url": "https://example.invalid/cli.whl", "sha256": "a" * 64,
        "version": "1.4.112" if channel == "stable" else "1.4.0-preview.2",
        "train": channel,
        "create_args": f"--ops-train {channel} --description 'source deployment'{source_selector}",
    }
    scenarios = builder["process_scenarios"]([{
        "name": "upgrade-path", "requires_baseline": True, "create_args": "--feature opcua.mode=Disabled",
    }], "upgrade-path")
    row, = builder["expand_channels"](
        scenarios, channel, {channel: baseline}, create_args="--description target",
    )
    monkeypatch.setenv("azext_edge_baseline_extension_dir", "/baseline")
    monkeypatch.setenv("azext_edge_runtime_channel", channel)
    monkeypatch.setenv("azext_edge_preserve_runtime", "false")
    mocker.patch.object(tests, "configured_baseline", return_value=row["baseline"])
    mocker.patch.object(tests, "run")
    mocker.patch.object(tests, "assert_aio_init")
    verify = mocker.patch.object(tests, "assert_runtime")
    provision = mocker.patch.object(tests.subprocess, "run")
    tests.test_init_scenario({
        "additionalInitArgs": row["init_args"], "additionalCreateArgs": row["create_args"],
        "clusterName": "cluster", "resourceGroup": "rg", "schemaRegistryId": "/registry",
        "adrNamespaceId": "/namespace", "instanceName": "instance",
    }, [])
    provision.assert_called_once()
    assert provision.call_args.args[0] == [
        "az", "iot", "ops", "create", "-g", "rg", "--cluster", "cluster", "-n", "instance",
        "--sr-resource-id", "/registry", "--ns-resource-id", "/namespace", "--no-progress",
        *shlex.split(baseline["create_args"]),
    ]
    assert provision.call_args.kwargs["env"]["AZURE_EXTENSION_DIR"] == "/baseline"
    verify.assert_called_once_with("instance", "rg", channel, baseline)


def test_matrix_main_wires_checkbox_selection_and_discovery(monkeypatch, tmp_path):
    builder = run_path(str(ROOT / ".github/actions/build-int-test-matrix/build_matrix.py"))
    config = tmp_path / "scenarios.yml"
    config.write_text("scenarios:\n  - name: edge\n")
    output = tmp_path / "matrix"
    baseline = {
        "wheel_url": "https://example.invalid/a.whl", "sha256": "a" * 64,
        "version": "1.4.112", "train": "stable", "create_args": "",
    }

    def discover(generations):
        assert generations == [1, 2]
        return {"n-1": baseline, "n-2": {**baseline, "version": "1.3.137"}}

    monkeypatch.setattr("runpy.run_path", lambda _: {"discover_previous": discover})
    for key, value in {
        "TEST_SCENARIO_FILE": str(config), "GITHUB_OUTPUT": str(output), "TEST_SCENARIOS": "",
        "TEST_CURRENT": "false", "TEST_N_1": "true", "TEST_N_2": "true",
        "RUNTIME_CHANNELS": "preview", "UPGRADE_BASELINES": "{}",
        "RUNTIME_INIT_ARGS": "", "RUNTIME_CREATE_ARGS": "",
    }.items():
        monkeypatch.setenv(key, value)
    builder["main"]()
    rows = json.loads(output.read_text().partition("=")[2])
    assert [row["name"] for row in rows] == ["edge-stable-n-1", "edge-stable-n-2"]
    assert [row["baseline"]["version"] for row in rows] == ["1.4.112", "1.3.137"]


@pytest.fixture
def compatibility_init(mocker, monkeypatch):
    from azext_edge.tests.edge.init.int import test_init_int as tests

    baseline = {"version": "1.4.112", "train": "stable", "create_args": "--ops-version 1.4.112"}
    for key, value in {
        "azext_edge_baseline_extension_dir": "/baseline", "azext_edge_runtime_channel": "stable",
        "azext_edge_preserve_runtime": "true", "AZURE_EXTENSION_DIR": "/candidate",
    }.items():
        monkeypatch.setenv(key, value)
    mocker.patch.object(tests, "configured_baseline", return_value=baseline)
    mocker.patch.object(tests, "assert_aio_init")
    runtime = mocker.patch.object(tests, "assert_compat_runtime")
    roles = mocker.patch.object(tests, "assert_role_assignment")
    provision = mocker.patch.object(tests.subprocess, "run")
    setup = {
        "additionalInitArgs": "", "additionalCreateArgs": "",
        "clusterName": "cluster", "resourceGroup": "rg", "schemaRegistryId": "/registry",
        "adrNamespaceId": "/namespace", "instanceName": "instance",
        "redeployment": False, "continueOnError": True,
    }
    instance = {
        "name": "instance",
        "extendedLocation": {"name": "/locations/location"}, "tags": {"legacy": "tag"},
        "sku": {"name": "Essentials"},
        "properties": {
            "description": "Legacy description", "schemaRegistryRef": {"resourceId": "/registry"},
            "adrNamespaceRef": {"resourceId": "/namespace"}, "features": {"opcua": {"mode": "Disabled"}},
        },
    }
    persistence = {
        "maxSize": "10Gi", "encryption": {"mode": "Enabled"},
        "persistentVolumeClaimSpec": {"accessModes": ["ReadWriteOncePod"]},
        "stateStore": {"mode": "Custom", "stateStoreSettings": {"dynamic": {"mode": "Enabled"}}},
        "retain": {"mode": "Custom", "retainSettings": {"dynamic": {"mode": "Enabled"}}},
        "subscriberQueue": {"mode": "Custom", "subscriberQueueSettings": {"dynamic": {"mode": "Enabled"}}},
    }
    broker = {
        "name": "default", "properties": {
            "memoryProfile": "High", "persistence": persistence,
            "cardinality": {
                "backendChain": {"partitions": 5, "redundancyFactor": 7, "workers": 4},
                "frontend": {"replicas": 3, "workers": 6},
            },
        },
    }
    issuer = {"name": "customer", "kind": "Issuer"}
    listeners = [
        {"name": "default", "properties": {
            "serviceType": "LoadBalancer", "ports": [{"tls": {"certManagerCertificateSpec": {"issuerRef": issuer}}}],
        }},
        {"name": "default-insecure", "properties": {"ports": [{"port": 1883}]}},
        {"name": "legacy-extra-listener", "properties": {}},
    ]
    resources = {
        "instance": instance, "listed_instance": instance, "templates": [], "broker": broker,
        "listeners": listeners, "dataflow": {"properties": {"instanceCount": 3}},
    }

    def candidate(command, **kwargs):
        import os

        assert os.environ["AZURE_EXTENSION_DIR"] == "/candidate"
        if command.startswith(("az iot ops init ", "az iot ops delete ")) or kwargs.get("expect_failure"):
            return None
        responses = {
            "az iot ops show -n instance -g rg": resources["instance"],
            "az iot ops list -g rg": [resources["listed_instance"]],
            "az iot ops connector template list -g rg --instance instance": resources["templates"],
            "az iot ops broker list -g rg -i instance": [resources["broker"]],
            "az iot ops broker listener list -g rg -i instance -b default": resources["listeners"],
            "az iot ops broker listener show -b default -n default -g rg -i instance": resources["listeners"][0],
            "az iot ops dataflow profile list -g rg -i instance": [resources["dataflow"]],
        }
        assert command in responses, f"Unexpected candidate command: {command}"
        return responses[command]

    command = mocker.patch.object(tests, "run", side_effect=candidate)
    return tests, setup, resources, command, provision, runtime, roles


@pytest.mark.parametrize("setting,arguments", [
    ("feature", "--feature opcua.mode=Disabled"),
    ("templates", "--feature opcua.mode=Disabled"),
    ("sku-show", "--sku Essentials --feature opcua.mode=Stable"),
    ("sku-list", "--sku Essentials --feature opcua.mode=Stable"),
    ("persistence", "--persist-max-size 10Gi"),
    ("listener", "--add-insecure-listener"),
    ("cardinality", "--broker-backend-part 5"),
    ("memory", "--broker-mem-profile High"),
    ("listener-type", "--broker-listener-type LoadBalancer"),
    ("dataflow", "--dataflow-profile-instances 3"),
    ("trust", "--trust-settings issuerName=customer issuerKind=Issuer"),
    ("tags", "--tags legacy=tag"),
    ("description", "--description expected"),
])
@pytest.mark.parametrize("matches", [True, False])
def test_compatibility_checks_actual_scenario_settings(compatibility_init, setting, arguments, matches):
    from copy import deepcopy

    tests, setup, resources, command, provision, _, roles = compatibility_init
    setup["additionalCreateArgs"] = arguments
    if setting.startswith("sku-"):
        resources["instance"]["properties"]["features"]["opcua"]["mode"] = "Stable"
        resources["listed_instance"] = deepcopy(resources["instance"])
    if setting == "description":
        resources["instance"]["properties"]["description"] = "expected"
    if not matches:
        if setting == "feature":
            resources["instance"]["properties"]["features"]["opcua"]["mode"] = "Stable"
        elif setting == "templates":
            resources["templates"] = [{"name": f"{tests.OPCUA_CONNECTOR_TEMPLATE_NAME_PREFIX}-unexpected"}]
        elif setting.startswith("sku-"):
            key = "instance" if setting == "sku-show" else "listed_instance"
            resources[key]["sku"]["name"] = "Standard"
        elif setting == "persistence":
            resources["broker"]["properties"]["persistence"]["maxSize"] = "3Gi"
        elif setting == "listener":
            resources["listeners"].pop(1)
        elif setting == "cardinality":
            resources["broker"]["properties"]["cardinality"]["backendChain"]["partitions"] = 2
        elif setting == "memory":
            resources["broker"]["properties"]["memoryProfile"] = "Low"
        elif setting == "listener-type":
            resources["listeners"][0]["properties"]["serviceType"] = "ClusterIp"
        elif setting == "dataflow":
            resources["dataflow"]["properties"]["instanceCount"] = 1
        elif setting == "trust":
            resources["listeners"][0]["properties"]["ports"][0]["tls"]["certManagerCertificateSpec"][
                "issuerRef"
            ]["name"] = "unexpected"
        elif setting == "tags":
            resources["instance"]["tags"] = {}
        elif setting == "description":
            resources["instance"]["properties"]["description"] = "unexpected"
        with pytest.raises(AssertionError):
            tests.test_init_scenario(setup, [])
    else:
        tests.test_init_scenario(setup, [])
    provision.assert_called_once()
    assert provision.call_args.kwargs["env"]["AZURE_EXTENSION_DIR"] == "/baseline"
    assert any(call.args[0] == "az iot ops show -n instance -g rg" for call in command.call_args_list)
    roles.assert_not_called()


def test_compatibility_omitted_settings_do_not_require_current_defaults(compatibility_init):
    tests, setup, _, command, _, _, roles = compatibility_init
    tests.test_init_scenario(setup, [])
    assert [call.args[0] for call in command.call_args_list] == [
        "az iot ops init -g rg --cluster cluster --no-progress  ",
        "az iot ops show -n instance -g rg",
    ]
    roles.assert_not_called()


def test_compatibility_partial_broker_config_checks_only_requested_fields(compatibility_init, tmp_path):
    tests, setup, resources, _, _, _, _ = compatibility_init
    config = tmp_path / "broker.json"
    config.write_text(json.dumps({"properties": {"memoryProfile": "High"}}))
    setup["additionalCreateArgs"] = f"--broker-config-file {config}"
    tests.test_init_scenario(setup, [])
    resources["broker"]["properties"]["memoryProfile"] = "Low"
    with pytest.raises(AssertionError):
        tests.test_init_scenario(setup, [])


def test_compatibility_redeployment_keeps_baseline_and_checks_scenario(compatibility_init):
    tests, setup, _, command, provision, runtime, _ = compatibility_init
    setup.update(redeployment=True, additionalCreateArgs="--feature opcua.mode=Disabled")
    tests.test_init_scenario(setup, [])
    assert provision.call_count == 2
    assert provision.call_args_list[0] == provision.call_args_list[1]
    assert runtime.call_count == 2
    commands = [call.args[0] for call in command.call_args_list]
    assert any(command.startswith("az iot ops delete ") for command in commands)
    assert "az iot ops connector template list -g rg --instance instance" in commands


@pytest.mark.parametrize("channel", ["stable", "preview"])
def test_current_provisioning_still_checks_defaults(mocker, monkeypatch, channel):
    from azext_edge.tests.edge.init.int import test_init_int as tests

    monkeypatch.setenv("azext_edge_runtime_channel", channel)
    monkeypatch.delenv("azext_edge_preserve_runtime", raising=False)
    mocker.patch.object(tests, "configured_baseline", return_value=None)
    mocker.patch.object(tests, "assert_aio_init")
    command = mocker.patch.object(tests, "run")
    runtime = mocker.patch.object(tests, "assert_runtime")
    assertions = [
        mocker.patch.object(tests, name) for name in (
            "assert_aio_instance", "assert_broker_args", "assert_dataflow_profile_args", "assert_trust_config_args",
        )
    ]
    tests.test_init_scenario({
        "additionalInitArgs": "", "additionalCreateArgs": "--use-preview" if channel == "preview" else "",
        "clusterName": "cluster", "resourceGroup": "rg", "schemaRegistryId": "/registry",
        "adrNamespaceId": "/namespace", "instanceName": "instance",
        "redeployment": False, "continueOnError": False,
    }, [])
    assert command.call_count == 2
    assert command.call_args.args[0].startswith("az iot ops create ")
    runtime.assert_called_once_with("instance", "rg", channel, None)
    for assertion in assertions:
        assertion.assert_called_once()
        assert assertion.call_args.kwargs["check_defaults"] is True
        assert assertion.call_args.kwargs.get("use_preview", False) == (channel == "preview")
