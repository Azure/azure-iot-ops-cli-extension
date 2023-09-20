# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Optional

import pytest

from azext_edge.edge.commands_edge import init
from azext_edge.edge.common import DeployableAioVersions
from azext_edge.edge.providers.orchestration import (
    get_aio_version_def,
    extension_name_to_type_map,
    EdgeServiceMoniker,
)

from ...generators import generate_generic_id


@pytest.mark.parametrize(
    "cluster_name,cluster_namespace,rg,custom_location_name,location,aio_version,processor_instance_name",
    [
        pytest.param(
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            DeployableAioVersions.v011.value,
            generate_generic_id(),
        ),
        pytest.param(
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            None,  # custom_location_name
            None,  # location
            DeployableAioVersions.v011.value,
            None,  # processor_instance_name
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
    aio_version,
    processor_instance_name,
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
    )

    template = partial_init(
        show_template=True,
        aio_version=DeployableAioVersions.v011.value,
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
        aio_version=aio_version,
        processor_instance_name=processor_instance_name,
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
    aio_version: str,
    custom_version: Optional[dict] = None,
    processor_instance_name: Optional[str] = None,
):
    if not custom_version:
        custom_version = {}
    k8s_extensions = find_resource_type(
        resources=resources, resource_type="Microsoft.KubernetesConfiguration/extensions"
    )
    assert len(k8s_extensions) == len(extension_name_to_type_map)
    cluster_extension_ids = []
    version_def = get_aio_version_def(version=aio_version)
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
        cluster_name=cluster_name,
        namespace=cluster_namespace,
        versions=version_def.moniker_to_version_map,
    )


def find_resource_type(resources: dict, resource_type: str) -> dict:
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


def assert_symphony_target(target: dict, cluster_name: str, namespace: str, versions: dict):
    assert target["apiVersion"] == "2023-05-22-preview"
    assert target["dependsOn"] == [
        "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]"
    ]
    assert target["extendedLocation"] == {
        "name": "[resourceId('Microsoft.ExtendedLocation/customLocations', variables('customLocationName'))]",
        "type": "CustomLocation",
    }
    assert target["location"] == "[variables('location')]"
    assert target["name"] == f"{cluster_name}-azedge-init-target"
    assert target["type"] == "Microsoft.Symphony/targets"
    assert target["properties"]["displayName"] == f"{cluster_name}-azedge-init-target"
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
            continue
        if component["name"] == "opc-ua-broker":
            assert component["properties"]["chart"]["repo"] == "alicesprings.azurecr.io/helm/az-e4i"
            assert component["properties"]["chart"]["version"] == versions[EdgeServiceMoniker.opcua.value]
            assert component["type"] == "helm.v3"
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


default_symphony_target_topologies = [
    {
        "bindings": [
            {"config": {"inCluster": "True"}, "provider": "providers.target.k8s", "role": "instance"},
            {"config": {"inCluster": "True"}, "provider": "providers.target.helm", "role": "helm.v3"},
            {"config": {"inCluster": "True"}, "provider": "providers.target.kubectl", "role": "yaml.k8s"},
        ]
    }
]
