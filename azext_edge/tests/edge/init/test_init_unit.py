# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from types import SimpleNamespace
from typing import Optional

import pytest

from azext_edge.edge.commands_edge import init
from azext_edge.edge.common import DeployableAioVersions

from ...generators import generate_generic_id


@pytest.mark.parametrize(
    "cluster_name,cluster_namespace,rg,custom_location_name,location,aio_version",
    [
        pytest.param(
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            DeployableAioVersions.v011.value,
        ),
        pytest.param(
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            generate_generic_id(),
            None,
            DeployableAioVersions.v011.value,
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
):
    partial_init = partial(
        init,
        cmd=mocked_cmd,
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        resource_group_name=rg,
        custom_location_name=custom_location_name,
        location=location,
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
        template["variables"],
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        custom_location_name=custom_location_name,
        location=location,
    )

    assert_resources(
        template["resources"],
        cluster_name=cluster_name,
        cluster_namespace=cluster_namespace,
        custom_location_name=custom_location_name,
        aio_version=aio_version,
        location=location,
    )


def assert_template_variables(
    variables: dict,
    cluster_name: str,
    cluster_namespace: str,
    custom_location_name: str,
    location: Optional[str] = None,
):
    assert variables["clusterId"] == f"[resourceId('Microsoft.Kubernetes/connectedClusters', '{cluster_name}')]"
    assert variables["customLocationNamespace"] == cluster_namespace
    assert variables["customLocationName"] == custom_location_name
    assert variables["extensionInfix"] == "/providers/Microsoft.KubernetesConfiguration/extensions/"
    assert variables["location"] == location if location else "[resourceGroup().location]"
    assert variables["targetName"] == f"{cluster_name}-{cluster_namespace}-init-target"


def assert_resources(
    resources: dict,
    cluster_name: str,
    cluster_namespace: str,
    custom_location_name: str,
    aio_version: str,
    custom_version: dict = None,
    location: Optional[str] = None,
):
    if not custom_version:
        custom_version = {}
    k8s_extensions = find_resource_type(
        resources=resources, resource_type="Microsoft.KubernetesConfiguration/extensions"
    )
    if aio_version == DeployableAioVersions.v011.value:
        pass

    import pdb

    pdb.set_trace()
    pass


def find_resource_type(resources: dict, resource_type: str):
    return [r for r in resources if r["type"] == resource_type]


def assert_k8s_extension(extension: dict, ext_type: str, name: str):
    pass
