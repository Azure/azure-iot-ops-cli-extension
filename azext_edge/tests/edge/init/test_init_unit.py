# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Dict, Optional

import pytest

from azext_edge.edge.commands_edge import init
from azext_edge.edge.common import DeployableAioVersions
from azext_edge.edge.providers.orchestration import EdgeServiceMoniker, extension_name_to_type_map, get_aio_version_def
from azext_edge.edge.util import assemble_nargs_to_dict

from ...generators import generate_generic_id


@pytest.mark.parametrize(
    "cluster_name,cluster_namespace,rg,custom_location_name,location,pas_version,"
    "processor_instance_name,simulate_plc,opcua_discovery_endpoint,create_sync_rules,"
    "custom_version,target_name",
    [
        pytest.param(
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),  # rg
            generate_generic_id(),  # custom_location_name
            generate_generic_id(),  # location
            DeployableAioVersions.v011.value,
            generate_generic_id(),  # processor_instance_name
            False,  # simulate_plc
            generate_generic_id(),  # opcua_discovery_endpoint
            True,  # create_sync_rules
            None,  # custom_version
            generate_generic_id(),  # target_name
        ),
        pytest.param(
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),  # rg
            None,  # custom_location_name
            None,  # location
            DeployableAioVersions.v011.value,
            None,  # processor_instance_name
            True,  # simulate_plc
            None,  # opcua_discovery_endpoint
            False,  # create_sync_rules
            ["e4k=1.0.0", "symphony=1.2.3"],  # custom_version
            None,  # target_name
        ),
    ],
)
def test_init_show_template(
    mocked_cmd,
    mocked_get_subscription_id,
    cluster_name,
    cluster_namespace,
    rg,
    custom_location_name,
    location,
    pas_version,
    processor_instance_name,
    simulate_plc,
    opcua_discovery_endpoint,
    create_sync_rules,
    custom_version,
    target_name,
):
    partial_init = partial(
        init,
        cmd=mocked_cmd,
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        resource_group_name=rg,
        custom_location_name=custom_location_name,
        location=location,
        processor_instance_name=processor_instance_name,
        simulate_plc=simulate_plc,
        opcua_discovery_endpoint=opcua_discovery_endpoint,
        create_sync_rules=create_sync_rules,
        custom_version=custom_version,
        target_name=target_name,
    )

    template = partial_init(
        show_template=True,
        pas_version=DeployableAioVersions.v011.value,
    )
    assert template["$schema"] == "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
    assert template["metadata"]["description"] == "Az Edge CLI PAS deployment."
    # TODO template versioning. Think about custom.
    assert template["contentVersion"] == "0.1.1.0"

    assert_template_variables(
        variables=template["variables"],
        cluster_name=cluster_name,
        custom_location_name=custom_location_name,
        location=location,
    )

    assert_resources(
        template["resources"],
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        custom_location_name=custom_location_name,
        pas_version=pas_version,
        processor_instance_name=processor_instance_name,
        simulate_plc=simulate_plc,
        opcua_discovery_endpoint=opcua_discovery_endpoint,
        create_sync_rules=create_sync_rules,
        custom_version=custom_version,
        target_name=target_name,
    )


def assert_template_variables(
    variables: dict,
    cluster_name: str,
    custom_location_name: str,
    location: Optional[str] = None,
):
    assert variables["clusterId"] == f"[resourceId('Microsoft.Kubernetes/connectedClusters', '{cluster_name}')]"
    assert (
        variables["customLocationName"] == custom_location_name
        if custom_location_name
        else f"{cluster_name}-azedge-init"
    )
    assert variables["extensionInfix"] == "/providers/Microsoft.KubernetesConfiguration/extensions/"
    assert variables["location"] == location if location else "[resourceGroup().location]"


def assert_resources(
    resources: dict,
    cluster_name: str,
    cluster_namespace: str,
    custom_location_name: str,
    pas_version: str,
    processor_instance_name: Optional[str] = None,
    simulate_plc: Optional[bool] = None,
    opcua_discovery_endpoint: Optional[str] = None,
    create_sync_rules: Optional[str] = None,
    custom_version: Optional[str] = None,
    target_name: Optional[str] = None,
):
    if not custom_version:
        custom_version = {}
    else:
        custom_version = assemble_nargs_to_dict(custom_version)

    k8s_extensions = find_resource_type(
        resources=resources, resource_type="Microsoft.KubernetesConfiguration/extensions"
    )
    assert len(k8s_extensions) == len(extension_name_to_type_map)
    cluster_extension_ids = []
    version_def = get_aio_version_def(version=pas_version)
    version_def.set_moniker_to_version_map(moniker_map=custom_version)
    for ext_name in k8s_extensions:
        assert_k8s_extension_common(
            extension=k8s_extensions[ext_name],
            cluster_name=cluster_name,
            extension_type=extension_name_to_type_map[ext_name],
            namespace=cluster_namespace,
            version=version_def.extension_to_vers_map[extension_name_to_type_map[ext_name]],
            config_settings=None,  # TODO
        )
        cluster_extension_ids.append(f"[concat(variables('clusterId'), variables('extensionInfix'), '{ext_name}')]")

    custom_locations = find_resource_type(
        resources=resources, resource_type="Microsoft.ExtendedLocation/customLocations"
    )
    assert len(custom_locations) == 1
    assert_custom_location(
        custom_location=next(iter(custom_locations.values())),
        name=custom_location_name,
        cluster_name=cluster_name,
        namespace=cluster_namespace,
        depends_on=cluster_extension_ids,
        cluster_ext_ids=cluster_extension_ids,
    )

    bluefin_instances = find_resource_type(resources=resources, resource_type="Microsoft.Bluefin/instances")
    assert len(bluefin_instances) == 1
    assert_bluefin_instance(
        instance=next(iter(bluefin_instances.values())), cluster_name=cluster_name, name=processor_instance_name
    )

    symphony_targets = find_resource_type(resources=resources, resource_type="Microsoft.Symphony/targets")
    assert len(symphony_targets) == 1
    assert_symphony_target(
        target=next(iter(symphony_targets.values())),
        name=target_name,
        cluster_name=cluster_name,
        namespace=cluster_namespace,
        versions=version_def.moniker_to_version_map,
        simulate_plc=simulate_plc,
        opcua_discovery_endpoint=opcua_discovery_endpoint,
    )

    if create_sync_rules:
        resource_sync_rules = find_resource_type(
            resources=resources, resource_type="Microsoft.ExtendedLocation/customLocations/resourceSyncRules"
        )
        for rule_name in resource_sync_rules:
            # extension type is rule_name.split("-")[1]
            extension_type = rule_name.split("-")[1]
            assert extension_type in version_def.extension_to_rp_map
            assert_resource_sync_rule(
                rule=resource_sync_rules[rule_name],
                custom_location=custom_location_name,
                extension_type=extension_type,
                resource_provider=version_def.extension_to_rp_map[extension_type],
            )


def find_resource_type(resources: dict, resource_type: str) -> Dict[str, dict]:
    return {r["name"]: r for r in resources if r["type"] == resource_type}


def assert_k8s_extension_common(
    extension: dict, cluster_name: str, extension_type: str, namespace: str, version: str, config_settings: dict = None
):
    if not config_settings:
        config_settings = {}

    assert extension["apiVersion"] == "2022-03-01"
    assert extension["name"]
    assert extension["properties"]["extensionType"] == extension_type
    assert extension["properties"]["autoUpgradeMinorVersion"] is False
    assert extension["properties"]["scope"]["cluster"]["releaseNamespace"] == namespace
    assert extension["properties"]["version"] == version
    assert extension["properties"]["releaseTrain"] == "private-preview"
    # assert extension["properties"]["configurationSettings"] == config_settings
    assert extension["scope"] == f"Microsoft.Kubernetes/connectedClusters/{cluster_name}"
    assert extension["type"] == "Microsoft.KubernetesConfiguration/extensions"


def assert_custom_location(
    custom_location: dict,
    cluster_name: str,
    namespace: str,
    depends_on: list = None,
    cluster_ext_ids: str = None,
    name: str = None,
):
    if not depends_on:
        depends_on = []

    if not cluster_ext_ids:
        cluster_ext_ids = []

    assert custom_location["apiVersion"] == "2021-08-31-preview"
    assert custom_location["dependsOn"] == depends_on
    assert custom_location["location"] == "[variables('location')]"
    assert custom_location["name"] == name if name else f"{cluster_name}-azedge-init"
    assert custom_location["properties"]["clusterExtensionIds"] == cluster_ext_ids
    assert custom_location["properties"]["displayName"] == name if name else f"{cluster_name}-azedge-init"
    assert custom_location["properties"]["hostResourceId"] == "[variables('clusterId')]"
    assert custom_location["properties"]["namespace"] == namespace
    assert custom_location["type"] == "Microsoft.ExtendedLocation/customLocations"


def assert_symphony_target(
    target: dict,
    name: str,
    cluster_name: str,
    namespace: str,
    versions: dict,
    simulate_plc: Optional[bool] = None,
    opcua_discovery_endpoint: Optional[str] = None,
):
    assert target["apiVersion"] == "2023-05-22-preview"
    assert target["dependsOn"] == [
        "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]"
    ]
    assert target["extendedLocation"] == {
        "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]",
        "type": "CustomLocation",
    }
    assert target["location"] == "[variables('location')]"
    assert target["name"] == name if name else f"{cluster_name}-azedge-init-target"
    assert target["type"] == "Microsoft.Symphony/targets"
    assert target["properties"]["displayName"] == name if name else f"{cluster_name}-azedge-init-target"
    assert target["properties"]["scope"] == namespace
    assert target["properties"]["topologies"] == default_symphony_target_topologies

    for component in target["properties"]["components"]:
        if component["name"] == "observability":
            assert component["properties"]["chart"]["repo"] == "alicesprings.azurecr.io/helm/opentelemetry-collector"
            assert component["properties"]["chart"]["version"] == versions[EdgeServiceMoniker.obs.value]
            assert component["type"] == "helm.v3"
            continue
        if component["name"] == "e4in":
            assert component["properties"]["chart"]["repo"] == "alicesprings.azurecr.io/az-e4in"
            assert component["properties"]["chart"]["version"] == versions[EdgeServiceMoniker.e4in.value]
            assert component["type"] == "helm.v3"
            continue
        if component["name"] == "akri":
            assert component["properties"]["chart"]["repo"] == "alicesprings.azurecr.io/helm/microsoft-managed-akri"
            assert component["properties"]["chart"]["version"] == versions[EdgeServiceMoniker.akri.value]
            assert component["type"] == "helm.v3"
            if simulate_plc and not opcua_discovery_endpoint:
                assert (
                    component["properties"]["values"]["custom"]["configuration"]["discoveryDetails"]
                    == f"opc.tcp://opcplc-000000.{namespace}:50000"
                )
            if opcua_discovery_endpoint:
                assert (
                    component["properties"]["values"]["custom"]["configuration"]["discoveryDetails"]
                    == opcua_discovery_endpoint
                )
            continue
        if component["name"] == "opc-ua-broker":
            assert component["properties"]["chart"]["repo"] == "alicesprings.azurecr.io/helm/az-e4i"
            assert component["properties"]["chart"]["version"] == versions[EdgeServiceMoniker.opcua.value]
            assert component["type"] == "helm.v3"
            assert component["properties"]["values"]["opcPlcSimulation"]["deploy"] == simulate_plc
            continue

        raise RuntimeError(f"Unknown symphony target component '{component['name']}'.")


def assert_bluefin_instance(instance: dict, cluster_name: str, name: str):
    assert instance["apiVersion"] == "2023-06-26-preview"
    assert instance["dependsOn"] == [
        "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]"
    ]
    assert instance["extendedLocation"] == {
        "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]",
        "type": "CustomLocation",
    }
    assert instance["location"] == "[variables('location')]"
    assert instance["name"] == name if name else f"{cluster_name}-azedge-init-instance"
    assert instance["properties"] == {}
    assert instance["type"] == "Microsoft.Bluefin/instances"


def assert_resource_sync_rule(rule: dict, custom_location: str, extension_type: str, resource_provider: str):
    assert rule["apiVersion"] == "2021-08-31-preview"
    assert rule["type"] == "Microsoft.ExtendedLocation/customLocations/resourceSyncRules"
    assert rule["dependsOn"] == [
        "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]"
    ]
    assert rule["location"] == "[variables('location')]"
    assert rule["name"] == f"{custom_location}/{custom_location}-{extension_type}-sync"

    assert isinstance(rule["properties"]["priority"], int)
    assert rule["properties"]["selector"] == {"matchLabels": {"management.azure.com/provider-name": resource_provider}}
    assert rule["properties"]["targetResourceGroup"] == "[resourceGroup().id]"


default_symphony_target_topologies = [
    {
        "bindings": [
            {"config": {"inCluster": "True"}, "provider": "providers.target.k8s", "role": "instance"},
            {"config": {"inCluster": "True"}, "provider": "providers.target.helm", "role": "helm.v3"},
            {"config": {"inCluster": "True"}, "provider": "providers.target.kubectl", "role": "yaml.k8s"},
        ]
    }
]
