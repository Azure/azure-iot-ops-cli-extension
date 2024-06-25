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
    dataprocessor = "Microsoft.IoTOperationsDataProcessor"
    mq = "Microsoft.IoTOperationsMQ/mq"
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
    _assert_aio_versions(result["deploymentState"]["opsVersion"], arg_dict.get("include_dp", False))
    _assert_deployment_resources(
        resources=result["deploymentState"]["resources"],
        cluster_name=cluster_name,
        resource_group=resource_group,
        **arg_dict
    )
    
    # Tls
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
    command = f"az resource show -g {resource_group} -n {resource_name} --resource-type {resource_type} --namespace {namespace}"
    command += f" --api-version {api_version}" if api_version else " -v"
    if len(split_id) > 3:
        command += f" --parent {'/'.join(split_id[1:-2])}"
    return run(command)


def _assert_aio_versions(aio_versions: Dict[str, str], include_dp: bool = False):
    from azext_edge.edge.providers.orchestration.template import CURRENT_TEMPLATE
    template_versions = CURRENT_TEMPLATE.get_component_vers(include_dp=include_dp)
    for key, value in aio_versions.items():
        assert value == template_versions[key]


def _assert_deployment_resources(resources: List[str], cluster_name: str, resource_group: str, **arg_dict):
    # only check the custom location + connected cluster resources
    resources.sort()
    ext_loc_resources = [res for res in resources if res.startswith(ResourceKeys.custom_location.value)]
    custom_loc_name = ext_loc_resources[0].split("/")[-1]
    expected_rules = ['adr', 'aio', 'mq']
    if arg_dict.get("include_dp"):
        expected_rules.append("dp")
    custom_loc_obj = get_resource_from_partial_id(ext_loc_resources[0], resource_group)
    assert custom_loc_obj["properties"]["hostResourceId"].endswith(cluster_name)
    extensions = custom_loc_obj["properties"]["clusterExtensionIds"]
    # should be the same number of extensions vs resource sync rules
    assert len(extensions) == len(expected_rules)

    assert len(ext_loc_resources) - 1 == len(expected_rules)
    for res in ext_loc_resources[1:]:
        assert custom_loc_name in res
        assert "resourceSyncRules" in res
        # get the service from custom-location-service-sync
        assert res.rsplit("-", maxsplit=2)[1] in expected_rules
        # check existance
        get_resource_from_partial_id(res, resource_group)

    # connected cluster resources
    con_clus_resources = [res for res in resources if res.startswith(ResourceKeys.connected_cluster.value)]
    expected_extensions = ["akri", "assets", "azure-iot-operations", "layered-networking", "mq", "opc-ua-broker"]
    if arg_dict.get("include_dp"):
        expected_extensions.append("processor")
    assert len(expected_extensions) == len(con_clus_resources)
    keyhash = con_clus_resources[0].rsplit("-")[-1]
    for res in con_clus_resources:
        assert cluster_name in res
        assert res.endswith(keyhash)
        ext_name = res.split("/")[-1]
        assert ext_name.rsplit("-", maxsplit=1)[0] in expected_extensions
