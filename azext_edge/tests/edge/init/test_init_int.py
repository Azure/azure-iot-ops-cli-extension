# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from typing import Dict, List
import pytest
from os import mkdir

from azext_edge.edge.providers.orchestration.common import KEYVAULT_ARC_EXTENSION_VERSION
from ...helpers import run
from ...generators import generate_names

class ResourceKeys(Enum):
    custom_location = "Microsoft.ExtendedLocation/customLocations"
    mq = "Microsoft.IoTOperationsMQ/mq"
    orchestrator = "Microsoft.IoTOperationsOrchestrator/targets"
    connected_cluster = "Microsoft.Kubernetes/connectedClusters"


@pytest.fixture(scope="function")
def cluster_cleanup(cluster_setup, settings, tracked_files):
    from ...settings import EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.cluster.value)
    settings.add_to_config(EnvironmentVariables.sp_app_id.value)
    settings.add_to_config(EnvironmentVariables.sp_object_id.value)

    cert_dir = "certificates"
    try:
        mkdir(cert_dir)
        tracked_files.append(cert_dir)
    except FileExistsError:
        pass
    
    yield {
        "clusterName": settings.env.azext_edge_cluster,
        "resourceGroup": settings.env.azext_edge_rg,
        "keyVault": settings.env.azext_edge_kv,
        "servicePrincipalAppId": settings.env.azext_edge_sp_app_id,
        "servicePrincipalObjectId": settings.env.azext_edge_sp_object_id,
        "CADirectory": cert_dir,
    }
    run(f"az iot ops delete --cluster {settings.env.azext_edge_cluster} -g {settings.env.azext_edge_rg} -y --no-progress --force")


@pytest.mark.parametrize("scenario", [
    pytest.param({"simulate_plc": True}, id="simualte plc"),
    pytest.param({
        "include_dp": True, "dp_instance": f"processor-{generate_names(max_length=5).lower()}"
    }, id="data processor")
])
def test_init_scenarios_test(
    settings, scenario, cluster_cleanup
):
    cluster_name = cluster_cleanup["clusterName"]
    resource_group = cluster_cleanup["resourceGroup"]
    key_vault = cluster_cleanup["keyVault"]
    sp_app_id = cluster_cleanup["servicePrincipalAppId"]
    sp_object_id = cluster_cleanup["servicePrincipalObjectId"]
    ca_dir = cluster_cleanup["CADirectory"]
    command = f"az iot ops init -g {resource_group} --cluster {cluster_name} "\
        f"--kv-id {key_vault} --no-progress --ca-dir {ca_dir} "
    if sp_app_id:
        command += f"--sp-app-id {sp_app_id} "

    for param, value in scenario.items():
        command += f"--{param.replace('_', '-')} "
        if not isinstance(value, bool):
            command += f"{value} "

    result = run(command)
    assert result
    assert result["deploymentState"]["status"] == "Succeeded", "AIO deployment failed"

    assert result["clusterName"] == settings.env.azext_edge_cluster
    assert result["clusterNamespace"] == scenario.get("cluster_namespace", "azure-iot-operations")
    assert result["deploymentLink"]
    assert result["deploymentName"]
    assert result["deploymentLink"].endswith(result["deploymentName"])

    # CSI driver
    assert result["csiDriver"]["keyVaultId"] == key_vault
    assert result["csiDriver"]["kvSpcSecretName"] == scenario.get("kv_spc_secret_name", "azure-iot-operations")
    assert result["csiDriver"]["version"] == scenario.get("csi_ver", KEYVAULT_ARC_EXTENSION_VERSION)
    
    if sp_app_id:
        assert result["csiDriver"]["spAppId"] == sp_app_id
    if sp_object_id:
        assert result["csiDriver"]["spObjectId"] == sp_object_id
    csi_config = result["csiDriver"]["configurationSettings"]
    enabled_rotation = 'false' if scenario.get("disable_rotation") else 'true'
    assert csi_config["secrets-store-csi-driver.enableSecretRotation"] == enabled_rotation
    assert csi_config["secrets-store-csi-driver.rotationPollInterval"] == scenario.get("rotation_int", "1h")
    assert csi_config["secrets-store-csi-driver.syncSecret.enabled"]

    # deployment state
    assert result["deploymentState"]["correlationId"]
    assert result["deploymentState"]["timestampUtc"]
    _assert_aio_versions(result["deploymentState"]["opsVersion"], scenario.get("include_dp", False))
    _assert_deployment_resources(
        resources=result["deploymentState"]["resources"],
        cluster_name=cluster_name,
        **scenario
    )
    
    # Tls
    assert result["tls"]["aioTrustConfigMap"]
    assert result["tls"]["aioTrustSecretName"]


def _assert_aio_versions(aio_versions: Dict[str, str], include_dp: bool = False):
    from azext_edge.edge.providers.orchestration.template import CURRENT_TEMPLATE
    template_versions = CURRENT_TEMPLATE.get_component_vers(include_dp=include_dp)
    for key, value in aio_versions.items():
        assert value == template_versions[key]


def _assert_deployment_resources(resources: List[str], cluster_name: str, **scenario):
    resources.sort()
    ext_loc_resources = [res for res in resources if res.startswith(ResourceKeys.custom_location.value)]
    custom_location = ext_loc_resources[0].split("/")[-1]
    sync_rules = []
    for res in ext_loc_resources[1:]:
        assert custom_location in res
        assert "resourceSyncRules" in res
        # get the service from custom-location-service-sync
        sync_rules.append(res.rsplit("-", maxsplit=2)[1])

    mq_resources = [res for res in resources if res.startswith(ResourceKeys.mq.value)]
    mq_name = mq_resources[0].split("/")[-1]
    if scenario.get("mq_instance"):
        pass
    else:
        assert mq_name.startswith("init-")
        assert mq_name.endswith("-mq-instance")

    for res in mq_resources[1:]:
        assert mq_name in res
    
    assert mq_resources[1].split("/")[-1] == scenario.get("mq_broker", "broker")
    assert mq_resources[2].split("/")[-1] == scenario.get("mq_authn", "authn")
    assert mq_resources[3].split("/")[-1] == scenario.get("mq_listener", "listener")
    assert mq_resources[4].split("/")[-1] == "diagnostics"

    orch_resources = [res for res in resources if res.startswith(ResourceKeys.orchestrator.value)]
    assert len(orch_resources) == 1
    orcherstrator = orch_resources[0].split("/")[-1]
    if scenario.get("target"):
        assert orcherstrator == scenario.get("target")
    else:
        assert orcherstrator.endswith("-ops-init-target")

    con_clus_resources = [res for res in resources if res.startswith(ResourceKeys.connected_cluster.value)]
    expected_extensions = ["akri", "assets", "azure-iot-operations", "layered-networking", "mq", "opc-ua-broker"]
    if scenario.get("include_dp"):
        expected_extensions.append("processor")
    assert len(expected_extensions) == len(con_clus_resources)
    keyhash = con_clus_resources[0].rsplit("-")[-1]
    for res in con_clus_resources:
        assert cluster_name in res
        assert res.endswith(keyhash)
        ext_name = res.split("/")[-1]
        assert ext_name.rsplit("-", maxsplit=1)[0] in expected_extensions
