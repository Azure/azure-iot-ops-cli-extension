# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from azext_edge.edge.providers.orchestration.common import KEYVAULT_ARC_EXTENSION_VERSION
from ....helpers import run


class ResourceKeys(Enum):
    custom_location = "Microsoft.ExtendedLocation/customLocations"
    iot_operations = "Microsoft.IoTOperations/instances"
    orchestrator = "Microsoft.IoTOperationsOrchestrator/targets"
    connected_cluster = "Microsoft.Kubernetes/connectedClusters"


def assert_init_result(
    result: Dict[str, Any],
    cluster_name: str,
    key_vault: str,
    resource_group: str,
    arg_dict: Dict[str, Union[str, bool]],
    sp_app_id: Optional[str] = None,
    sp_object_id: Optional[str] = None,
):
    assert result
    assert result["deploymentState"]["status"] == "Succeeded", "AIO deployment failed"

    assert result["clusterName"] == cluster_name
    assert result["clusterNamespace"] == arg_dict.get("cluster_namespace", "azure-iot-operations")
    assert result["deploymentLink"]
    assert result["deploymentName"]
    assert result["deploymentLink"].endswith(result["deploymentName"])

    # instance name (not in alphabetical but important enough)
    name = arg_dict.get("name")
    if not name:
        name = arg_dict.get("n")
    expected_name = name or f"{cluster_name}-ops-instance"
    assert result["instanceName"] == expected_name
    assert f"{ResourceKeys.iot_operations.value}/{expected_name}" in result["deploymentState"]["resources"]
    _assert_instance_show(
        instance_name=expected_name,
        resource_group=resource_group,
        ops_version=result["deploymentState"]["opsVersion"]["aio"],
        **arg_dict
    )

    # CSI driver
    assert result["csiDriver"]["keyVaultId"] == key_vault
    assert result["csiDriver"]["kvSpcSecretName"] == arg_dict.get("kv_spc_secret_name", "azure-iot-operations")
    assert result["csiDriver"]["version"] == arg_dict.get("csi_ver", KEYVAULT_ARC_EXTENSION_VERSION)

    if sp_app_id:
        assert result["csiDriver"]["spAppId"] == sp_app_id
    if sp_object_id:
        assert result["csiDriver"]["spObjectId"] == sp_object_id
    csi_config = result["csiDriver"]["configurationSettings"]
    enabled_rotation = 'false' if arg_dict.get("disable_rotation") else 'true'
    assert csi_config["secrets-store-csi-driver.enableSecretRotation"] == enabled_rotation
    assert csi_config["secrets-store-csi-driver.rotationPollInterval"] == arg_dict.get("rotation_int", "1h")
    assert csi_config["secrets-store-csi-driver.syncSecret.enabled"]

    # deployment state
    assert result["deploymentState"]["correlationId"]
    assert result["deploymentState"]["timestampUtc"]

    _assert_aio_versions(result["deploymentState"]["opsVersion"])
    _assert_deployment_resources(
        resources=result["deploymentState"]["resources"],
        cluster_name=cluster_name,
        resource_group=resource_group,
        **arg_dict
    )

    # Tls
    if arg_dict.get("no_tls"):
        assert "tls" not in result
    else:
        assert result["tls"]["aioTrustConfigMap"]
        assert result["tls"]["aioTrustSecretName"]


def get_resource_from_partial_id(
    partial_id: str,
    resource_group: str,
    api_version: Optional[str] = None,
):
    split_id = partial_id.split("/")
    resource_name = split_id[-1]
    resource_type = split_id[-2]
    namespace = split_id[0]
    command = f"az resource show -g {resource_group} -n {resource_name} --resource-type {resource_type} "\
        f"--namespace {namespace}"
    command += f" --api-version {api_version}" if api_version else " -v"
    if len(split_id) > 3:
        command += f" --parent {'/'.join(split_id[1:-2])}"
    return run(command)


def strip_quotes(argument: Optional[str]) -> Optional[str]:
    if not argument:
        return argument
    if argument[0] == argument[-1] and argument[0] in ("'", '"'):
        argument = argument[1:-1]
    return argument


def _assert_aio_versions(aio_versions: Dict[str, str]):
    from azext_edge.edge.providers.orchestration.template import CURRENT_TEMPLATE
    template_versions = CURRENT_TEMPLATE.get_component_vers()
    for key, value in aio_versions.items():
        assert value == template_versions[key]


def _assert_deployment_resources(resources: List[str], cluster_name: str, resource_group: str, **arg_dict):
    # only check the custom location + connected cluster resources
    resources.sort()
    ext_loc_resources = [res for res in resources if res.startswith(ResourceKeys.custom_location.value)]
    custom_loc_name = ext_loc_resources[0].split("/")[-1]

    custom_loc_obj = get_resource_from_partial_id(ext_loc_resources[0], resource_group)
    assert custom_loc_obj["properties"]["hostResourceId"].endswith(cluster_name)
    extensions = custom_loc_obj["properties"]["clusterExtensionIds"]
    expected_extensions = ["azure-iot-operations", "azure-iot-operations-platform"]
    assert len(extensions) == len(expected_extensions)

    expected_rules = ['adr', 'aio', 'mq']
    assert len(ext_loc_resources) - 1 == (0 if arg_dict.get("disable_rsync_rules") else len(expected_rules))
    for res in ext_loc_resources[1:]:
        assert custom_loc_name in res
        assert "resourceSyncRules" in res
        # get the service from custom-location-service-sync
        assert res.rsplit("-", maxsplit=2)[1] in expected_rules
        # check existance
        get_resource_from_partial_id(res, resource_group)

    # connected cluster resources
    con_clus_resources = [res for res in resources if res.startswith(ResourceKeys.connected_cluster.value)]
    assert len(expected_extensions) == len(con_clus_resources)
    keyhash = con_clus_resources[0].rsplit("-")[-1]
    for res in con_clus_resources:
        assert cluster_name in res
        assert res.endswith(keyhash)
        ext_name = res.split("/")[-1]
        assert ext_name.rsplit("-", maxsplit=1)[0] in expected_extensions


def _assert_instance_show(instance_name: str, resource_group: str, ops_version: str, **arg_dict):
    show_result = run(f"az iot ops show -n {instance_name} -g {resource_group}")

    assert show_result["extendedLocation"]["name"].endswith(arg_dict.get("custom_location", "-ops-init-cl"))
    assert show_result["extendedLocation"]["type"] == "CustomLocation"

    assert show_result["location"] == arg_dict.get(
        "location", run(f"az group show -n {resource_group}")["location"]
    ).lower()

    props = show_result["properties"]
    assert props.get("description") == strip_quotes(arg_dict.get("desc", ""))
    assert props["provisioningState"] == "Succeeded"
    assert props["version"] == ops_version
