# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from azure.cli.core.azclierror import CLIInternalError
import pytest
from knack.log import get_logger

from ....generators import generate_random_string
from ....helpers import run

logger = get_logger(__name__)

# pytest mark for rpsaas (cloud-side) tests
pytestmark = pytest.mark.rpsaas


@pytest.fixture(scope="function")
def instance_test_setup(settings):
    from ....settings import EnvironmentVariables
    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.instance.value)
    if not all([settings.env.azext_edge_instance, settings.env.azext_edge_rg]):
        raise AssertionError(
            "Cannot run instance tests without an instance and resource group. "
            f"Current settings:\n {settings}"
        )

    yield {
        "resourceGroup": settings.env.azext_edge_rg,
        "instanceName": settings.env.azext_edge_instance
    }


def test_aio_instance(instance_test_setup, tracked_resources):
    resource_group = instance_test_setup["resourceGroup"]
    instance_name = instance_test_setup["instanceName"]
    try:
        instance_rg_list = run(f"az iot ops list -g {resource_group}")
        assert instance_name in [inst["name"] for inst in instance_rg_list]
    except CLIInternalError:
        logger.error(f"Possible bad instance in resource group {resource_group}")

    try:
        instance_sub_list = run("az iot ops list")
        assert instance_name in [inst["name"] for inst in instance_sub_list]
    except CLIInternalError:
        sub = run("az account show").get("id", "current")
        logger.error(f"Possible bad instance in subscription `{sub}`.")

    tree = run(f"az iot ops show -n {instance_name} -g {resource_group} --tree")
    assert "azure-iot-operations-platform" in tree
    # instance name should be one of the resources
    assert instance_name in tree

    # create random resource to ensure it shows up in show tree
    aep_name = generate_random_string(force_lower=True)
    aep = run(
        f"az iot ops asset endpoint create opcua -n {aep_name} -g {resource_group} "
        f"--instance {instance_name} --target-address opc.tcp://opcplc-000000.azure-iot-operations:50000"
    )
    tracked_resources.append(aep["id"])
    tree = run(f"az iot ops show -n {instance_name} -g {resource_group} --tree")
    assert aep_name in tree

    instance_show = run(f"az iot ops show -n {instance_name} -g {resource_group}")
    if instance_show.get("properties", {}).get("provisioningState") != "Succeeded":
        pytest.skip("Cannot update instance that is not ready.")

    # update - ultimate sadness
    description = generate_random_string()
    tags = f"{generate_random_string()}={generate_random_string()}"
    instance_update = run(
        f"az iot ops update -n {instance_name} -g {resource_group} --description {description} "
        f"--tags {tags}"
    )
    assert instance_update["properties"]["description"] == description
    tag_key, tag_value = tags.split("=")
    assert instance_update["tags"][tag_key] == tag_value
