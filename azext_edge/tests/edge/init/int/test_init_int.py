# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from os import mkdir

from ....helpers import run
from .dataprocessor_helper import assert_dataprocessor_args
from .mq_helper import assert_mq_args
from .opcua_helper import assert_simulate_plc_args
from .orchestrator_helper import assert_orchestrator_args
from .helper import assert_init_result


@pytest.fixture(scope="function")
def init_test_setup(cluster_connection, settings):
    from ....settings import EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.kv.value)
    settings.add_to_config(EnvironmentVariables.cluster.value)
    settings.add_to_config(EnvironmentVariables.sp_app_id.value)
    settings.add_to_config(EnvironmentVariables.sp_object_id.value)
    settings.add_to_config(EnvironmentVariables.init_args.value)
    if not all([settings.env.azext_edge_cluster, settings.env.azext_edge_rg, settings.env.azext_edge_kv]):
        pytest.skip("Cannot run init tests without a connected cluster, resource group, and precreated keyvault.")
    if not any([settings.env.azext_edge_sp_app_id, settings.env.azext_edge_sp_object_id]):
        pytest.skip("Cannot run init tests without a service principal.")
    
    yield {
        "clusterName": settings.env.azext_edge_cluster,
        "resourceGroup": settings.env.azext_edge_rg,
        "keyVault": settings.env.azext_edge_kv,
        "servicePrincipalAppId": settings.env.azext_edge_sp_app_id,
        "servicePrincipalObjectId": settings.env.azext_edge_sp_object_id,
        "additionalArgs": settings.env.azext_edge_init_args.strip('"')
    }
    run(
        f"az iot ops delete --cluster {settings.env.azext_edge_cluster} -g {settings.env.azext_edge_rg} "
        "-y --no-progress --force"
    )


def test_init_scenario(
    init_test_setup, tracked_files
):
    additional_args = init_test_setup["additionalArgs"]
    arg_dict = {}
    for arg in additional_args.split("--"):
        arg = arg.replace("-", "_").strip().split(" ", maxsplit=1)
        # --simualte-plc vs --dp-instance dp_name
        if len(arg) == 1:
            arg_dict[arg[0]] = True
        else:
            arg_dict[arg[0]] = arg[1]
        
    if "ca_dir" in arg_dict:
        try:
            mkdir(arg_dict["ca_dir"])
            tracked_files.append(arg_dict["ca_dir"])
        except FileExistsError:
            pass
    elif all([
        "ca_key_file" not in arg_dict,
        "ca_file" not in arg_dict
    ]):
        tracked_files.append("aio-test-ca.crt")
        tracked_files.append("aio-test-private.key")
    
    cluster_name = init_test_setup["clusterName"]
    resource_group = init_test_setup["resourceGroup"]
    key_vault = init_test_setup["keyVault"]
    sp_app_id = init_test_setup["servicePrincipalAppId"]
    sp_object_id = init_test_setup["servicePrincipalObjectId"]

    command = f"az iot ops init -g {resource_group} --cluster {cluster_name} "\
        f"--kv-id {key_vault} --no-progress {additional_args} "
    if sp_app_id:
        command += f"--sp-app-id {sp_app_id} "
    if sp_object_id:
        command += f"--sp-object-id {sp_object_id} "

    result = run(command)
    # result = {
    #     "clusterName": "space-cod",
    #     "clusterNamespace": "azure-iot-operations",
    #     "csiDriver": {
    #         "configurationSettings": {
    #             "secrets-store-csi-driver.enableSecretRotation": "true",
    #             "secrets-store-csi-driver.rotationPollInterval": "1h",
    #             "secrets-store-csi-driver.syncSecret.enabled": "false"
    #         },
    #         "keyVaultId": "/subscriptions/a386d5ea-ea90-441a-8263-d816368c84a1/resourceGroups/vilit-clusters/providers/Microsoft.KeyVault/vaults/vilitclusterkv",
    #         "kvSpcSecretName": "azure-iot-operations",
    #         "spAppId": "ddcb4ebe-fe87-419d-b511-e74159757c3b",
    #         "spObjectId": "6273b097-7071-4005-b1de-be3dbe855e78",
    #         "version": "1.5.3"
    #     },
    #     "deploymentLink": "https://portal.azure.com/#blade/HubsExtension/DeploymentDetailsBlade/id/%2Fsubscriptions%2Fa386d5ea-ea90-441a-8263-d816368c84a1%2FresourceGroups%2Fvilit-clusters2%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2Faziotops.init.7141ead489b04ec48519270d91d02778",
    #     "deploymentName": "aziotops.init.7141ead489b04ec48519270d91d02778",
    #     "deploymentState": {
    #         "correlationId": "0848ae3b-23f1-4f50-a58b-3dfef222b8b1",
    #         "opsVersion": {
    #             "adr": "0.1.0-preview",
    #             "aio": "0.5.1-preview",
    #             "akri": "0.3.0-preview",
    #             "layeredNetworking": "0.1.0-preview",
    #             "mq": "0.4.0-preview",
    #             "observability": "0.1.0-preview",
    #             "opcUaBroker": "0.4.0-preview",
    #             "processor": "0.2.1-preview"
    #         },
    #         "resources": [
    #             "Microsoft.ExtendedLocation/customLocations/space-cod-lqnne-ops-init-cl",
    #             "Microsoft.ExtendedLocation/customLocations/space-cod-lqnne-ops-init-cl/resourceSyncRules/space-cod-lqnne-ops-init-cl-adr-sync",
    #             "Microsoft.ExtendedLocation/customLocations/space-cod-lqnne-ops-init-cl/resourceSyncRules/space-cod-lqnne-ops-init-cl-aio-sync",
    #             "Microsoft.ExtendedLocation/customLocations/space-cod-lqnne-ops-init-cl/resourceSyncRules/space-cod-lqnne-ops-init-cl-dp-sync",
    #             "Microsoft.ExtendedLocation/customLocations/space-cod-lqnne-ops-init-cl/resourceSyncRules/space-cod-lqnne-ops-init-cl-mq-sync",
    #             "Microsoft.IoTOperationsDataProcessor/instances/space-cod-ops-init-processor",
    #             "Microsoft.IoTOperationsMQ/mq/init-9e9b9-mq-instance",
    #             "Microsoft.IoTOperationsMQ/mq/init-9e9b9-mq-instance/broker/broker",
    #             "Microsoft.IoTOperationsMQ/mq/init-9e9b9-mq-instance/broker/broker/authentication/authn",
    #             "Microsoft.IoTOperationsMQ/mq/init-9e9b9-mq-instance/broker/broker/listener/listener",
    #             "Microsoft.IoTOperationsMQ/mq/init-9e9b9-mq-instance/diagnosticService/diagnostics",
    #             "Microsoft.IoTOperationsOrchestrator/targets/space-cod-ops-init-target",
    #             "Microsoft.Kubernetes/connectedClusters/space-cod/providers/Microsoft.KubernetesConfiguration/extensions/akri-encln",
    #             "Microsoft.Kubernetes/connectedClusters/space-cod/providers/Microsoft.KubernetesConfiguration/extensions/assets-encln",
    #             "Microsoft.Kubernetes/connectedClusters/space-cod/providers/Microsoft.KubernetesConfiguration/extensions/azure-iot-operations-encln",
    #             "Microsoft.Kubernetes/connectedClusters/space-cod/providers/Microsoft.KubernetesConfiguration/extensions/layered-networking-encln",
    #             "Microsoft.Kubernetes/connectedClusters/space-cod/providers/Microsoft.KubernetesConfiguration/extensions/mq-encln",
    #             "Microsoft.Kubernetes/connectedClusters/space-cod/providers/Microsoft.KubernetesConfiguration/extensions/opc-ua-broker-encln",
    #             "Microsoft.Kubernetes/connectedClusters/space-cod/providers/Microsoft.KubernetesConfiguration/extensions/processor-encln"
    #         ],
    #         "status": "Succeeded",
    #         "timestampUtc": {
    #             "ended": "2024-06-24T18:36:17",
    #             "started": "2024-06-24T18:27:31"
    #         }
    #     },
    #     "resourceGroup": "vilit-clusters2",
    #     "tls": {
    #         "aioTrustConfigMap": "aio-ca-trust-bundle-test-only",
    #         "aioTrustSecretName": "aio-ca-key-pair-test-only"
    #     }
    # }
    assert_init_result(
        result=result,
        cluster_name=cluster_name,
        key_vault=key_vault,
        resource_group=resource_group,
        arg_dict=arg_dict,
        sp_app_id=sp_app_id,
        sp_object_id=sp_object_id
    )

    custom_location = sorted(result["deploymentState"]["resources"])[0]

    for assertion in [
        assert_dataprocessor_args, 
        assert_simulate_plc_args,
        assert_mq_args,
        assert_orchestrator_args
    ]:
        assertion(
            namespace=result["clusterNamespace"], 
            cluster_name=cluster_name, 
            custom_location=custom_location,
            resource_group=resource_group,
            init_resources=result["deploymentState"]["resources"],
            **arg_dict
        )
