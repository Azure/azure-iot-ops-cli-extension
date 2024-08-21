# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

# TODO: temporary while delete is borked
from azure.cli.core.azclierror import CLIInternalError

from ....generators import generate_random_string
from ....helpers import run

def test_schema_registry_lifecycle(tracked_resources):
    storage_account_name = f"teststore{generate_random_string(force_lower=True, size=6)}"
    registry_name = f"test-registry-{generate_random_string(force_lower=True, size=6)}"
    registry_rg = "vilit-clusters"
    registry_namespace = f"test-namespace-{generate_random_string(force_lower=True, size=6)}"
    # create the storage account and get the id
    storage_account = run(
        f"az storage account create -n {storage_account_name} -g {registry_rg} "
        "--enable-hierarchical-namespace"
    )
    tracked_resources.append(storage_account['id'])

    # CREATE 1
    registry = run(
        f"az iot ops schema registry create -n {registry_name} -g {registry_rg} "
        f"--rn {registry_namespace} --sa-resource-id {storage_account['id']} "
        "--location eastus2euap"  # TODO: remove once avaliable in all regions
    )
    tracked_resources.append(registry["id"])
    assert_schema_registry(
        registry=registry,
        name=registry_name,
        resource_group=registry_rg,
        namespace=registry_namespace,
        sa_blob_uri=storage_account["primaryEndpoints"]["blob"]
    )
    # check the roles
    roles = run(
        f"az role assignment list --assignee {registry['identity']['principalId']} "
        f"--scope {storage_account['id']}"
    )
    assert roles
    assert roles[0]["roleDefinitionName"] == "Storage Blob Data Contributor"

    # SHOW
    show_registry = run(
        f"az iot ops schema registry show -n {registry_name} -g {registry_rg}"
    )
    assert_schema_registry(
        registry=show_registry,
        name=registry_name,
        resource_group=registry_rg,
        namespace=registry_namespace,
        sa_blob_uri=storage_account["primaryEndpoints"]["blob"]
    )

    # CREATE 2 no update so new registry
    # get a role id
    role_name = "Storage Blob Data Owner"
    role_id = run(f"az role definition list --name \"{role_name}\" --query [*].id -o tsv").strip()

    alt_registry_name = f"test-registry-{generate_random_string(force_lower=True, size=6)}"
    sa_container = generate_random_string(force_lower=True, size=8)
    description = generate_random_string()
    display_name = generate_random_string()
    tags = f"{generate_random_string()}={generate_random_string()}"
    alt_registry = run(
        f"az iot ops schema registry create -n {alt_registry_name} -g {registry_rg} "
        f"--rn {registry_namespace} --sa-resource-id {storage_account['id']} "
        f"--sa-container {sa_container} --desc {description} --display-name {display_name} "
        f"--tags {tags} --custom-role-id {role_id} "
        "--location eastus2euap"  # TODO: remove once avaliable in all regions
    )
    tracked_resources.append(alt_registry["id"])
    assert_schema_registry(
        registry=registry,
        name=registry_name,
        resource_group=registry_rg,
        namespace=registry_namespace,
        sa_blob_uri=storage_account["primaryEndpoints"]["blob"]
    )
    # check the roles
    roles = run(
        f"az role assignment list --assignee {alt_registry['identity']['principalId']} "
        f"--scope {storage_account['id']}"
    )
    assert roles
    assert roles[0]["roleDefinitionName"] == role_name

    # LIST
    list_registry_sub = run("az iot ops schema registry list")
    list_registry_names = [reg["name"] for reg in list_registry_sub]
    assert registry_name in list_registry_names
    assert alt_registry_name in list_registry_names

    # DELETE
    try:
        run(f"az iot ops schema registry delete -n {registry_name} -g {registry_rg} -y")
    except CLIInternalError as e:
        # delete does not return correct status code - remove once fixed
        if "ERROR: Operation returned an invalid status 'OK'" not in e.error_msg:
            raise e

    list_registry_rg = run(f"az iot ops schema registry list -g {registry_rg}")
    list_registry_names = [reg["name"] for reg in list_registry_rg]
    assert registry_name not in list_registry_names
    assert alt_registry_name in list_registry_names

    # DELETE 2
    try:
        run(f"az iot ops schema registry delete -n {alt_registry_name} -g {registry_rg} -y")
    except CLIInternalError as e:
        # delete does not return correct status code - remove once fixed
        if "ERROR: Operation returned an invalid status 'OK'" not in e.error_msg:
            raise e


def assert_schema_registry(registry: dict, **expected):
    assert registry["name"] == expected["name"]
    assert registry["resourceGroup"] == expected["resource_group"]

    assert registry["identity"]

    registry_props = registry["properties"]
    assert registry_props["namespace"] == expected["namespace"]
    assert registry_props["storageAccountContainerUrl"].startswith(expected["sa_blob_uri"])
    assert registry_props["storageAccountContainerUrl"].endswith(expected.get("sa_container", "schemas"))
    assert registry_props.get("description") == expected.get("description")
    assert registry_props.get("displayName") == expected.get("display_name")

