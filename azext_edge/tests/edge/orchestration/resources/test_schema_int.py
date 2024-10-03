# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

# TODO: temporary while delete is borked
from azure.cli.core.azclierror import CLIInternalError

from ....generators import generate_random_string
from ....helpers import run


def test_schema_lifecycle(settings_with_rg, tracked_resources):
    storage_account_name = f"teststore{generate_random_string(force_lower=True, size=6)}"
    registry_name = f"test-registry-{generate_random_string(force_lower=True, size=6)}"
    registry_rg = settings_with_rg.env.azext_edge_rg
    registry_namespace = f"test-namespace-{generate_random_string(force_lower=True, size=6)}"
    # create the storage account and get the id
    storage_account = run(
        f"az storage account create -n {storage_account_name} -g {registry_rg} "
        "--enable-hierarchical-namespace --public-network-access Disabled "
        "--allow-shared-key-access false --allow-blob-public-access false --default-action Deny"
    )
    tracked_resources.append(storage_account['id'])

    # create the registry
    registry = run(
        f"az iot ops schema registry create -n {registry_name} -g {registry_rg} "
        f"--rn {registry_namespace} --sa-resource-id {storage_account['id']} "
    )
    tracked_resources.append(registry["id"])

    # CREATE 1
    schema_name1 = f"schema-{generate_random_string(force_lower=True, size=6)}"
    schema_name2 = f"schema-{generate_random_string(force_lower=True, size=6)}"
    schema1 = run(
        f"az iot ops schema create -n {schema_name1} -g {registry_rg} --registry {registry_name} "
        "--format json --type MessageSchema"
    )
    assert_schema(
        schema=schema1,
        name=schema_name1,
        resource_group=registry_rg,
        registry_name=registry_name,
        schema_type="MessageSchema",
        format="json"
    )

    # SHOW
    schema_show = run(f"az iot ops schema show -n {schema_name1} -g {registry_rg} --registry {registry_name}")
    assert_schema(
        schema=schema_show,
        name=schema_name1,
        resource_group=registry_rg,
        registry_name=registry_name,
        schema_type="MessageSchema",
        format="json"
    )

    # CREATE 2
    description = f"{generate_random_string()} {generate_random_string()}"
    display_name = generate_random_string()
    schema2 = run(
        f"az iot ops schema create -n {schema_name2} -g {registry_rg} --registry {registry_name} "
        f"--format delta --type MessageSchema --desc \"{description}\" --display-name {display_name}"
    )
    assert_schema(
        schema=schema2,
        name=schema_name2,
        resource_group=registry_rg,
        registry_name=registry_name,
        schema_type="MessageSchema",
        format="delta",
        description=description,
        display_name=display_name
    )

    # LIST
    schema_list = run(f"az iot ops schema list -g {registry_rg} --registry {registry_name}")
    schema_names = [schema["name"] for schema in schema_list]
    assert schema_name1 in schema_names
    assert schema_name2 in schema_names

    # DELETE
    run(f"az iot ops schema delete -n {schema_name1} -g {registry_rg} --registry {registry_name} -y")
    run(f"az iot ops schema delete -n {schema_name2} -g {registry_rg} --registry {registry_name} -y")


def assert_schema(schema: dict, **expected):
    format_map = {
        "json": "JsonSchema/draft-07",
        "delta": "Delta/1.0"
    }
    assert schema["name"] == expected["name"]
    assert schema["resourceGroup"] == expected["resource_group"]
    # note: trying to do exact name match hence split
    assert expected["registry_name"] in schema["id"].split("/")

    schema_props = schema["properties"]
    assert schema_props["schemaType"] == expected["schema_type"]
    assert schema_props["format"] == format_map[expected["format"]]
    assert schema_props.get("description") == expected.get("description")
    assert schema_props.get("displayName") == expected.get("display_name")
