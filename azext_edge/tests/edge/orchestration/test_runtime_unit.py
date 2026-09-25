# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from copy import deepcopy
from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError

from azext_edge.edge.providers.orchestration.common import CUSTOM_LOCATIONS_API_VERSION
from azext_edge.edge.providers.orchestration.resources.instances import Instances
from azext_edge.edge.providers.orchestration.runtime import (
    OperationRequirements,
    ParameterRequirement,
    resolve_runtime,
    validate_operation,
)
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel, RuntimeIdentity


INSTANCE_ID = "/subscriptions/instance-sub/resourceGroups/instance-rg/providers/Microsoft.IoTOperations/instances/aio"
CL_ID = "/subscriptions/cluster-sub/resourceGroups/cluster-rg/providers/Microsoft.ExtendedLocation/customLocations/cl"
CLUSTER_ID = "/subscriptions/cluster-sub/resourceGroups/cluster-rg/providers/Microsoft.Kubernetes/connectedClusters/arc"
EXTENSION_ID = CLUSTER_ID + "/providers/Microsoft.KubernetesConfiguration/extensions/aio"


@pytest.fixture
def records():
    return {
        "instance": {
            "id": INSTANCE_ID,
            "extendedLocation": {"name": CL_ID},
            "properties": {"provisioningState": "Succeeded", "version": "not-used-as-installed-version"},
        },
        "custom_location": {
            "id": CL_ID,
            "properties": {
                "hostResourceId": CLUSTER_ID,
                "clusterExtensionIds": [EXTENSION_ID],
                "provisioningState": "Succeeded",
            },
        },
        "cluster": {"id": CLUSTER_ID, "properties": {"connectivityStatus": "Connected"}},
        "extensions": [{
            "id": EXTENSION_ID,
            "properties": {
                "extensionType": "microsoft.iotoperations",
                "currentVersion": "1.5.7",
                "version": "1.5.7",
                "releaseTrain": "Stable",
                "provisioningState": "Succeeded",
            },
        }],
    }


def test_runtime_resolution_is_read_only_and_uses_installed_version(records):
    original = deepcopy(records)
    runtime = resolve_runtime(**records)
    runtime.require_ready()
    assert runtime.identity == RuntimeIdentity(RuntimeChannel.STABLE, "1.5.7", "stable")
    assert runtime.cluster_id == CLUSTER_ID
    assert runtime.instance_id == INSTANCE_ID
    assert records == original


def test_requested_version_never_replaces_installed_version(records):
    properties = records["extensions"][0]["properties"]
    properties["version"] = "1.5.8"
    runtime = resolve_runtime(**records)
    assert runtime.identity.version == "1.5.7"
    assert runtime.requested_version == "1.5.8"
    with pytest.raises(ValidationError, match="differs from installed"):
        runtime.require_ready()
    del properties["currentVersion"]
    with pytest.raises(ValidationError, match="currentVersion is missing"):
        resolve_runtime(**records)


def test_requested_version_is_optional(records):
    del records["extensions"][0]["properties"]["version"]
    runtime = resolve_runtime(**records)
    assert runtime.requested_version is None
    runtime.require_ready()


@pytest.mark.parametrize("state", ["Failed", "Canceled"])
def test_known_failed_runtime_can_be_reconciled(records, state):
    properties = records["extensions"][0]["properties"]
    properties.update(provisioningState=state, version="1.5.8", errorInfo={"message": "upgrade failed"})
    runtime = resolve_runtime(**records)
    with pytest.raises(ValidationError):
        runtime.require_ready()
    runtime.require_upgradeable()


def test_repair_does_not_ignore_other_readiness_failures(records):
    records["extensions"][0]["properties"]["provisioningState"] = "Failed"
    records["cluster"]["properties"]["connectivityStatus"] = "Disconnected"
    with pytest.raises(ValidationError, match="disconnected"):
        resolve_runtime(**records).require_upgradeable()


@pytest.mark.parametrize("state", [None, "Failed", "Creating", "Updating", "Deleting", "Canceled"])
@pytest.mark.parametrize("record_name", ["instance", "custom_location", "extension"])
def test_unready_runtime_rejected(records, state, record_name):
    record = records["extensions"][0] if record_name == "extension" else records[record_name]
    record["properties"]["provisioningState"] = state
    runtime = resolve_runtime(**records)
    with pytest.raises(ValidationError, match="not ready"):
        OperationRequirements("update").validate(runtime)


@pytest.mark.parametrize("error", ["disconnected", "errorInfo", "statuses"])
def test_runtime_reports_errors(records, error):
    if error == "disconnected":
        records["cluster"]["properties"]["connectivityStatus"] = "Disconnected"
    elif error == "errorInfo":
        records["extensions"][0]["properties"][error] = {"code": "failed"}
    else:
        records["extensions"][0]["properties"][error] = [{"level": "Error"}]
    with pytest.raises(ValidationError, match="not ready"):
        resolve_runtime(**records).require_ready()


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_duplicate_aio_extension_rejected(records, count):
    records["extensions"] *= count
    with pytest.raises(ValidationError, match="exactly one"):
        resolve_runtime(**records)


@pytest.mark.parametrize("mismatch", ["location", "host", "extension", "association", "invalid-id"])
def test_relationship_mismatch_rejected(records, mismatch):
    if mismatch == "location":
        records["custom_location"]["id"] += "-other"
    elif mismatch == "host":
        records["cluster"]["id"] += "-other"
    elif mismatch == "extension":
        records["extensions"][0]["id"] = EXTENSION_ID.replace("connectedClusters/arc", "connectedClusters/other")
    elif mismatch == "association":
        records["custom_location"]["properties"]["clusterExtensionIds"] = []
    else:
        records["instance"]["extendedLocation"]["name"] = "cl"
    with pytest.raises(ValidationError):
        resolve_runtime(**records)


def test_arm_id_matching_is_case_insensitive(records):
    records["custom_location"]["id"] = CL_ID.upper()
    records["cluster"]["id"] = CLUSTER_ID.upper()
    records["custom_location"]["properties"]["clusterExtensionIds"] = [EXTENSION_ID.upper()]
    resolve_runtime(**records).require_ready()


def test_integration_does_not_imply_preview(records):
    records["extensions"][0]["properties"]["releaseTrain"] = "integration"
    with pytest.raises(ValidationError, match="no supported runtime profile mapping"):
        resolve_runtime(**records)
    identity = RuntimeIdentity(RuntimeChannel.STABLE, "1.5.7", "integration")
    assert resolve_runtime(**records, qualification_identities=[identity]).identity == identity


@pytest.mark.parametrize("preview", [False, True])
def test_shared_command_and_preview_only_parameter(records, preview):
    if preview:
        records["extensions"][0]["properties"].update(
            currentVersion="1.6.0-preview.4", version="1.6.0-preview.4", releaseTrain="preview"
        )
    runtime = resolve_runtime(**records)
    shared = OperationRequirements("GA command")
    restricted = OperationRequirements("--test-option", frozenset({RuntimeChannel.PREVIEW}))
    parameters = [ParameterRequirement("test_option", restricted)]
    validate_operation(runtime, shared, {}, parameters)
    validate_operation(runtime, shared, {"test_option": None}, parameters)
    writer = Mock()
    if preview:
        validate_operation(runtime, shared, {"test_option": False}, parameters)
        writer()
        writer.assert_called_once()
    else:
        with pytest.raises(ValidationError, match="requires a preview runtime"):
            validate_operation(runtime, shared, {"test_option": False}, parameters)
            writer()
        writer.assert_not_called()


def test_restrict_only_selected_values(records):
    runtime = resolve_runtime(**records)
    shared = OperationRequirements("GA command")
    restriction = ParameterRequirement(
        "mode", OperationRequirements("--mode experimental", {RuntimeChannel.PREVIEW}), {"experimental"}
    )
    validate_operation(runtime, shared, {"mode": "ordinary"}, [restriction])
    with pytest.raises(ValidationError, match="requires a preview runtime"):
        validate_operation(runtime, shared, {"mode": ["ordinary", "experimental"]}, [restriction])


@pytest.mark.parametrize(
    "arguments,values,expected",
    [({}, None, False), ({"option": None}, None, False), ({"option": False}, None, True),
     ({"option": 0}, None, True), ({"option": ""}, None, True),
     ({"option": False}, {True}, False), ({"option": True}, {True}, True)],
)
def test_parameter_presence_not_truthiness(arguments, values, expected):
    restriction = ParameterRequirement("option", OperationRequirements("test"), values)
    assert restriction.applies(arguments) is expected


@pytest.mark.parametrize("minimum,maximum", [("1.5.8", None), (None, "1.5.7")])
def test_shared_capability_still_requires_compatible_version(records, minimum, maximum):
    with pytest.raises(ValidationError, match="requires AIO version"):
        OperationRequirements("test", minimum_version=minimum, maximum_version_exclusive=maximum).validate(
            resolve_runtime(**records)
        )


def test_discovery_uses_cluster_subscription_and_only_reads(records, mocker):
    # Bypass constructor/authentication: exercise only the read-only discovery method.
    provider = Instances.__new__(Instances)
    provider.default_subscription_id = "instance-sub"
    provider._arm_endpoint = "https://management.azure.com/"
    provider.resource_client = Mock()
    provider.resource_client.resources.get_by_id.return_value = records["custom_location"]
    prefix = "azext_edge.edge.providers.orchestration.resources.instances."
    clusters = mocker.patch(prefix + "get_connectedk8s_mgmt_client")
    extensions = mocker.patch(prefix + "get_clusterconfig_mgmt_client")
    clusters.return_value.connected_cluster.get.return_value = records["cluster"]
    extensions.return_value.extensions.list.return_value = iter(records["extensions"])
    runtime = provider.get_runtime_context(records["instance"])
    runtime.require_ready()
    provider.resource_client.resources.get_by_id.assert_called_once_with(
        resource_id=CL_ID, api_version=CUSTOM_LOCATIONS_API_VERSION
    )
    kwargs = {"subscription_id": "cluster-sub", "endpoint": "https://management.azure.com/"}
    clusters.assert_called_once_with(**kwargs)
    extensions.assert_called_once_with(**kwargs)
    clusters.return_value.connected_cluster.get.assert_called_once_with(
        resource_group_name="cluster-rg", cluster_name="arc"
    )
    extensions.return_value.extensions.list.assert_called_once_with(
        resource_group_name="cluster-rg", cluster_rp="Microsoft.Kubernetes",
        cluster_resource_name="connectedClusters", cluster_name="arc"
    )
    assert [call[0] for call in extensions.return_value.mock_calls] == ["extensions.list"]
    assert [call[0] for call in clusters.return_value.mock_calls] == ["connected_cluster.get"]


def test_discovery_propagates_read_failure_without_fallback(records):
    provider = Instances.__new__(Instances)
    provider.resource_client = Mock()
    provider.resource_client.resources.get_by_id.side_effect = HttpResponseError("Forbidden")
    with pytest.raises(HttpResponseError, match="Forbidden"):
        provider.get_runtime_context(records["instance"])


def test_null_connectivity_is_unknown_not_ready(records):
    records["cluster"]["properties"]["connectivityStatus"] = None
    with pytest.raises(ValidationError, match="connectivity is unknown"):
        resolve_runtime(**records).require_ready()


@pytest.mark.parametrize("statuses", ["unknown", {}, [None]])
def test_invalid_status_information_is_not_ready(records, statuses):
    records["extensions"][0]["properties"]["statuses"] = statuses
    with pytest.raises(ValidationError, match="status information is invalid"):
        resolve_runtime(**records).require_ready()


def test_invalid_requirement_version_range():
    with pytest.raises(ValidationError, match="Invalid runtime version range"):
        OperationRequirements("test", minimum_version="1.5.7", maximum_version_exclusive="1.5.7")
