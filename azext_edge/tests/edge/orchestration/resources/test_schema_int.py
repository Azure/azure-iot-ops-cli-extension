# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


import json
from ....generators import generate_random_string
from ....helpers import run


def test_schema_lifecycle(settings_with_rg, tracked_resources, tracked_files):
    storage_account_name = f"teststore{generate_random_string(force_lower=True, size=6)}"
    registry_name = f"test-registry-{generate_random_string(force_lower=True, size=6)}"
    registry_rg = settings_with_rg.env.azext_edge_rg
    registry_namespace = f"test-namespace-{generate_random_string(force_lower=True, size=6)}"
    # create the storage account and get the id
    # NOTE: storage account needs to have public network access enabled to work.
    storage_account = run(
        f"az storage account create -n {storage_account_name} -g {registry_rg} "
        "--enable-hierarchical-namespace "
        "--allow-shared-key-access false --allow-blob-public-access false --default-action Deny"
    )
    tracked_resources.append(storage_account['id'])

    # create the registry
    registry = run(
        f"az iot ops schema registry create -n {registry_name} -g {registry_rg} "
        f"--rn {registry_namespace} --sa-resource-id {storage_account['id']} "
    )
    tracked_resources.append(registry["id"])

    # CREATE 1 with min version args
    schema_name1 = f"schema-{generate_random_string(force_lower=True, size=6)}"
    schema_name2 = f"schema-{generate_random_string(force_lower=True, size=6)}"
    delta_content = generate_random_string()
    version_num = 1
    schema1 = run(
        f"az iot ops schema create -n {schema_name1} -g {registry_rg} --registry {registry_name} "
        f"--format delta --type MessageSchema --version-content {delta_content}"
    )
    assert_schema(
        schema=schema1,
        name=schema_name1,
        resource_group=registry_rg,
        registry_name=registry_name,
        schema_type="MessageSchema",
        format="delta"
    )

    # there should be a blob in the storage account once the version is created but need to figure out how to
    # get that with identity (rather than connection strings/etc
    # )

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

    # SHOW VERSION
    version_show = run(
        f"az iot ops schema version show -n {version_num} --schema {schema_name1} -g {registry_rg} "
        f"--registry {registry_name}"
    )
    assert_schema_version(
        version=version_show,
        name=version_num,
        schema_name=schema_name1,
        registry_name=registry_name,
        schema_content=delta_content
    )

    # CREATE 2 with max version args
    description = f"{generate_random_string()} {generate_random_string()}"
    display_name = generate_random_string()

    version_desc = generate_random_string()
    version_num = 14
    json_content = json.dumps({
        generate_random_string(): generate_random_string(),
        generate_random_string(): {
            generate_random_string(): generate_random_string()
        },
        generate_random_string(): generate_random_string()
    })
    file_name = f"test_schema_content_{generate_random_string(size=4)}.json"
    tracked_files.append(file_name)
    with open(file_name, "w", encoding="utf-8") as f:
        f.write(json_content)

    schema2 = run(
        f"az iot ops schema create -n {schema_name2} -g {registry_rg} --registry {registry_name} "
        f"--format json --type MessageSchema --desc \"{description}\" --display-name {display_name}"
        f"--vc {file_name} --vd {version_desc} --ver {version_num}"
    )
    assert_schema(
        schema=schema2,
        name=schema_name2,
        resource_group=registry_rg,
        registry_name=registry_name,
        schema_type="MessageSchema",
        format="json",
        description=description,
        display_name=display_name
    )

    # ADD VERSION
    inline_content = json.dumps({
        generate_random_string(): generate_random_string(),
        generate_random_string(): generate_random_string()
    })
    version_add = run(
        f"az iot ops schema version add -n {version_num + 2} --schema {schema_name2} -g {registry_rg} "
        f"--registry {registry_name} --content {inline_content}"
    )
    assert_schema_version(
        version=version_add,
        name=version_num + 2,
        schema_name=schema_name2,
        registry_name=registry_name,
        schema_content=inline_content,
    )

    # LIST VERSION
    version_list = run(
        f"az iot ops schema version list --schema {schema_name2} -g {registry_rg} "
        f"--registry {registry_name}"
    )
    version_map = {int(ver["name"]): ver for ver in version_list}
    assert version_num in version_map
    assert version_num + 2 in version_map
    assert_schema_version(
        version=version_map[version_num],
        name=version_num,
        schema_name=schema_name2,
        registry_name=registry_name,
        schema_content=json_content,
        description=version_desc
    )

    # DELETE VERSION
    run(
        f"az iot ops schema version delete -n {version_num} --schema {schema_name1} -g {registry_rg} "
        f"--registry {registry_name}"
    )

    # LIST
    version_list = run(
        f"az iot ops schema version list --schema {schema_name2} -g {registry_rg} "
        f"--registry {registry_name}"
    )
    version_map = [ver["name"] for ver in version_list]
    assert version_num not in version_map
    assert version_num + 2 in version_map

    # LIST
    schema_list = run(f"az iot ops schema list -g {registry_rg} --registry {registry_name}")
    schema_names = [schema["name"] for schema in schema_list]
    assert schema_name1 in schema_names
    assert schema_name2 in schema_names

    # DELETE
    run(f"az iot ops schema delete -n {schema_name1} -g {registry_rg} --registry {registry_name} -y")
    run(f"az iot ops schema delete -n {schema_name2} -g {registry_rg} --registry {registry_name} -y")
    schema_list = run(f"az iot ops schema list -g {registry_rg} --registry {registry_name}")
    schema_names = [schema["name"] for schema in schema_list]
    assert schema_name1 not in schema_names
    assert schema_name2 not in schema_names


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


def assert_schema_version(version: dict, **expected):
    assert version["name"] == str(expected["name"])
    assert version["resourceGroup"] == expected["resource_group"]
    # note: trying to do exact name match hence split
    assert expected["registry_name"] in version["id"].split("/")
    assert expected["schema_name"] in version["id"].split("/")

    assert version["properties"]["hash"]
    assert version["properties"]["schemaContent"] == expected["schema_content"]
    assert version["properties"].get("description") == expected.get("description")
