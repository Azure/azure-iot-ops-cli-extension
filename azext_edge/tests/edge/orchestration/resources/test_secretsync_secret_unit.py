# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from typing import List, Optional

import pytest
import responses
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.commands_secretsync import (
    secretsync_secret_list,
    secretsync_secret_set,
    secretsync_secret_remove,
)
from azext_edge.edge.providers.orchestration.resources.instances import (
    SERVICE_ACCOUNT_SECRETSYNC,
)
from ....generators import generate_random_string, generate_resource_id
from .conftest import (
    ARG_ENDPOINT,
    BASE_URL,
)
from .test_secretsync_spcs_unit import get_mock_spc_record, get_spc_endpoint
from .test_secretsyncs_unit import get_mock_secretsync_record, get_secretsync_endpoint
from .test_instances_unit import get_instance_endpoint, get_mock_instance_record


KEYVAULT_DATA_URL_RE = re.compile(r"https://[^/]+\.vault\.azure\.net/secrets/.*")


def _setup_instance_and_spc(
    mocked_responses: responses,
    instance_name: str,
    resource_group_name: str,
    spc_name: str,
    keyvault_name: str = "mykeyvault",
    spc_objects: Optional[str] = None,
    mock_vault_url: bool = True,
):
    """Helper to set up instance + SPC fetch mocks for set/unset tests."""
    # Instance endpoint
    instance_endpoint = get_instance_endpoint(
        resource_group_name=resource_group_name, instance_name=instance_name
    )
    spc_resource_id = generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider="Microsoft.SecretSyncController",
        resource_path=f"/azureKeyVaultSecretProviderClasses/{spc_name}",
    )
    instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
        default_spc_resource_id=spc_resource_id,
    )
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=instance_record,
        status=200,
        content_type="application/json",
    )

    # SPC fetch
    spc_endpoint = get_spc_endpoint(
        resource_group_name=resource_group_name, spc_name=spc_name
    )
    spc_record = get_mock_spc_record(
        name=spc_name,
        resource_group_name=resource_group_name,
    )
    spc_record["properties"]["keyvaultName"] = keyvault_name
    if spc_objects is not None:
        spc_record["properties"]["objects"] = spc_objects
    else:
        spc_record["properties"]["objects"] = ""

    mocked_responses.add(
        method=responses.GET,
        url=spc_endpoint,
        json=spc_record,
        status=200,
        content_type="application/json",
    )

    # ARG mock for vault URL resolution
    if mock_vault_url:
        mocked_responses.add(
            method=responses.POST,
            url=ARG_ENDPOINT,
            json={"data": [{"properties_vaultUri": f"https://{keyvault_name}.vault.azure.net/"}]},
            status=200,
            content_type="application/json",
        )

    return instance_record, spc_record


# --- secretsync secret set ---


@pytest.mark.parametrize(
    "secret_map, existing_secretsync",
    [
        # Create new SecretSync with one secret
        (["mysecret=certificate"], False),
        # Create new SecretSync with multiple secrets
        (["mysecret1=certificate", "mysecret2=privateKey"], False),
        # Merge into existing SecretSync
        (["newsecret=intermediateCerts"], True),
        # Add same sourcePath with different targetKey (allowed — multi-key mapping)
        (["secret1=newTargetKey"], True),
    ],
)
def test_secretsync_secret_set(
    mocked_cmd,
    mocked_responses: responses,
    secret_map: List[str],
    existing_secretsync: bool,
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    secret_sync_name = generate_random_string()
    spc_name = generate_random_string()
    keyvault_name = "mykeyvault"

    _, spc_record = _setup_instance_and_spc(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        spc_name=spc_name,
        keyvault_name=keyvault_name,
    )

    # Mock KV secret verification for each secret name
    for entry in secret_map:
        akv_name = entry.split("=")[0]
        mocked_responses.add(
            method=responses.GET,
            url=KEYVAULT_DATA_URL_RE,
            json={"value": "secretvalue", "id": f"https://{keyvault_name}.vault.azure.net/secrets/{akv_name}"},
            status=200,
            content_type="application/json",
        )

    # Mock SPC PUT (update)
    spc_put = mocked_responses.add(
        method=responses.PUT,
        url=get_spc_endpoint(resource_group_name=resource_group_name, spc_name=spc_name),
        json=spc_record,
        status=200,
        content_type="application/json",
    )

    # Mock SecretSync GET (exists or 404)
    ss_endpoint = get_secretsync_endpoint(
        resource_group_name=resource_group_name, spc_name=secret_sync_name
    )
    if existing_secretsync:
        existing_ss = get_mock_secretsync_record(
            name=secret_sync_name, resource_group_name=resource_group_name
        )
        mocked_responses.add(
            method=responses.GET,
            url=ss_endpoint,
            json=existing_ss,
            status=200,
            content_type="application/json",
        )
    else:
        mocked_responses.add(
            method=responses.GET,
            url=ss_endpoint,
            json={"error": {"code": "ResourceNotFound"}},
            status=404,
            content_type="application/json",
        )

    # Mock SecretSync PUT (create or update)
    expected_ss_result = get_mock_secretsync_record(
        name=secret_sync_name, resource_group_name=resource_group_name
    )
    ss_put = mocked_responses.add(
        method=responses.PUT,
        url=ss_endpoint,
        json=expected_ss_result,
        status=200,
        content_type="application/json",
    )

    result = secretsync_secret_set(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        secret_sync_name=secret_sync_name,
        secret_map=secret_map,
        wait_sec=0,
    )

    assert result == expected_ss_result

    # Verify SPC was updated
    spc_put_body = json.loads(spc_put.calls[0].request.body)
    assert "objects" in spc_put_body["properties"]

    # Verify SecretSync was created/updated
    ss_put_body = json.loads(ss_put.calls[0].request.body)
    ss_mappings = ss_put_body["properties"]["objectSecretMapping"]
    for entry in secret_map:
        akv_name, _, target_key = entry.partition("=")
        matching = [m for m in ss_mappings if m["sourcePath"] == akv_name and m["targetKey"] == target_key]
        assert len(matching) == 1

    if not existing_secretsync:
        assert ss_put_body["properties"]["secretProviderClassName"] == spc_name
        assert ss_put_body["properties"]["serviceAccountName"] == SERVICE_ACCOUNT_SECRETSYNC
        assert ss_put_body["properties"]["kubernetesSecretType"] == "Opaque"


@pytest.mark.parametrize(
    "kv_tags, expected_hex_encoding",
    [
        # DOE/CLI-uploaded cert: has file-encoding:hex tag → objectEncoding: hex in SPC
        ({"file-encoding": "hex"}, True),
        # Plain secret (password, token): no tag → no objectEncoding in SPC
        ({}, False),
        # Unrelated tags: no file-encoding tag → no objectEncoding
        ({"purpose": "tls"}, False),
    ],
)
def test_secretsync_secret_set_hex_encoding_detection(
    mocked_cmd,
    mocked_responses: responses,
    kv_tags: dict,
    expected_hex_encoding: bool,
):
    """Verify objectEncoding:hex in SPC is set iff AKV secret has tags['file-encoding']=='hex'.

    DOE and our CLI both set tags['file-encoding']='hex' when uploading DER/PEM certs.
    Content-type alone is NOT reliable (DER certs get 'application/pkix-cert' which
    does not contain 'pkcs12' or 'x-pem'). Tags are the authoritative signal.
    """
    import yaml

    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    secret_sync_name = generate_random_string()
    spc_name = generate_random_string()
    keyvault_name = "mykeyvault"
    akv_name = "my-cert-der"

    _, spc_record = _setup_instance_and_spc(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        spc_name=spc_name,
        keyvault_name=keyvault_name,
    )

    # Mock KV GET — return secret with or without the file-encoding tag
    mocked_responses.add(
        method=responses.GET,
        url=KEYVAULT_DATA_URL_RE,
        json={
            "value": "abc123",
            "id": f"https://{keyvault_name}.vault.azure.net/secrets/{akv_name}",
            "contentType": "application/pkix-cert",  # DER content type — not reliable for encoding
            "tags": kv_tags,
        },
        status=200,
        content_type="application/json",
    )

    # Capture SPC PUT body
    spc_put = mocked_responses.add(
        method=responses.PUT,
        url=get_spc_endpoint(resource_group_name=resource_group_name, spc_name=spc_name),
        json=spc_record,
        status=200,
        content_type="application/json",
    )

    # Mock SecretSync GET (not found → create)
    ss_endpoint = get_secretsync_endpoint(
        resource_group_name=resource_group_name, spc_name=secret_sync_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=ss_endpoint,
        json={"error": {"code": "ResourceNotFound"}},
        status=404,
        content_type="application/json",
    )
    expected_ss = get_mock_secretsync_record(
        name=secret_sync_name, resource_group_name=resource_group_name
    )
    mocked_responses.add(
        method=responses.PUT,
        url=ss_endpoint,
        json=expected_ss,
        status=200,
        content_type="application/json",
    )

    secretsync_secret_set(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        secret_sync_name=secret_sync_name,
        secret_map=[f"{akv_name}=certificate"],
        wait_sec=0,
    )

    # Inspect the SPC PUT body — check whether objectEncoding: hex was added
    spc_put_body = json.loads(spc_put.calls[0].request.body)
    objects_yaml = spc_put_body["properties"].get("objects", "")
    assert objects_yaml, "SPC objects YAML must not be empty"

    objects_obj = yaml.safe_load(objects_yaml)
    entries = [yaml.safe_load(e) for e in objects_obj.get("array", [])]
    matching = [e for e in entries if e.get("objectName") == akv_name]
    assert len(matching) == 1, f"Expected exactly one SPC entry for '{akv_name}'"

    spc_entry = matching[0]
    if expected_hex_encoding:
        assert spc_entry.get("objectEncoding") == "hex", (
            f"Expected objectEncoding:hex in SPC for secret with tags {kv_tags}"
        )
    else:
        assert "objectEncoding" not in spc_entry, (
            f"Expected no objectEncoding in SPC for secret with tags {kv_tags}"
        )


@pytest.mark.parametrize(
    "bad_secret_name",
    [
        "noseparator",
        "=onlytarget",
        "onlyakv=",
    ],
)
def test_secretsync_secret_set_invalid_format(
    mocked_cmd,
    mocked_responses: responses,
    bad_secret_name: str,
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    secret_sync_name = generate_random_string()
    spc_name = generate_random_string()

    _setup_instance_and_spc(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        spc_name=spc_name,
        mock_vault_url=False,
    )

    with pytest.raises(InvalidArgumentValueError):
        secretsync_secret_set(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            secret_sync_name=secret_sync_name,
            secret_map=[bad_secret_name],
            wait_sec=0,
        )


def test_secretsync_secret_set_akv_not_found(
    mocked_cmd,
    mocked_responses: responses,
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    secret_sync_name = generate_random_string()
    spc_name = generate_random_string()

    _setup_instance_and_spc(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        spc_name=spc_name,
    )

    # Mock KV secret NOT found (404)
    mocked_responses.add(
        method=responses.GET,
        url=KEYVAULT_DATA_URL_RE,
        json={"error": {"code": "SecretNotFound"}},
        status=404,
        content_type="application/json",
    )

    with pytest.raises(InvalidArgumentValueError, match="not found in Key Vault"):
        secretsync_secret_set(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            secret_sync_name=secret_sync_name,
            secret_map=["nonexistent=cert"],
            wait_sec=0,
        )


# --- secretsync secret list ---


def test_secretsync_secret_list(
    mocked_cmd,
    mocked_responses: responses,
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    secret_sync_name = generate_random_string()
    spc_name = generate_random_string()

    # list_secretsync_secrets calls get_default_spc first (instance GET + SPC GET)
    _setup_instance_and_spc(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        spc_name=spc_name,
        mock_vault_url=False,
    )

    ss_record = get_mock_secretsync_record(
        name=secret_sync_name, resource_group_name=resource_group_name
    )
    ss_endpoint = get_secretsync_endpoint(
        resource_group_name=resource_group_name, spc_name=secret_sync_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=ss_endpoint,
        json=ss_record,
        status=200,
        content_type="application/json",
    )

    result = secretsync_secret_list(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        secret_sync_name=secret_sync_name,
    )

    expected_mappings = ss_record["properties"]["objectSecretMapping"]
    assert result == expected_mappings
    assert len(result) == 2


def test_secretsync_secret_list_empty(
    mocked_cmd,
    mocked_responses: responses,
):
    """Verify list returns an empty list (not None) when objectSecretMapping is absent."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    secret_sync_name = generate_random_string()
    spc_name = generate_random_string()

    _setup_instance_and_spc(
        mocked_responses=mocked_responses,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        spc_name=spc_name,
        mock_vault_url=False,
    )

    ss_record = get_mock_secretsync_record(
        name=secret_sync_name, resource_group_name=resource_group_name
    )
    # Simulate a SecretSync with no mappings
    ss_record["properties"]["objectSecretMapping"] = []

    ss_endpoint = get_secretsync_endpoint(
        resource_group_name=resource_group_name, spc_name=secret_sync_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=ss_endpoint,
        json=ss_record,
        status=200,
        content_type="application/json",
    )

    result = secretsync_secret_list(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        secret_sync_name=secret_sync_name,
    )

    assert result == []
    assert result is not None


@pytest.mark.parametrize(
    "remaining_count, other_secretsyncs_reference",
    [
        # Remove one of two secrets, no other SS references
        (1, False),
        # Remove last secret (deletes the SS), no other SS references
        (0, False),
        # Remove one, another SS still references the same akv secret
        (1, True),
        # Remove last, another SS still references — SPC entry kept
        (0, True),
    ],
)
def test_secretsync_secret_remove(
    mocked_cmd,
    mocked_responses: responses,
    remaining_count: int,
    other_secretsyncs_reference: bool,
):
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    secret_sync_name = generate_random_string()
    spc_name = generate_random_string()
    keyvault_name = "mykeyvault"
    secret_to_remove = "secret1"

    # Build the initial SecretSync with appropriate mappings
    if remaining_count == 0:
        # Only one mapping — removing it means deleting the SS
        initial_mappings = [{"sourcePath": secret_to_remove, "targetKey": "password"}]
    else:
        initial_mappings = [
            {"sourcePath": secret_to_remove, "targetKey": "password"},
            {"sourcePath": "secret2", "targetKey": "username"},
        ]

    ss_record = get_mock_secretsync_record(
        name=secret_sync_name, resource_group_name=resource_group_name
    )
    ss_record["properties"]["objectSecretMapping"] = initial_mappings
    ss_record["properties"]["secretProviderClassName"] = spc_name
    ss_endpoint = get_secretsync_endpoint(
        resource_group_name=resource_group_name, spc_name=secret_sync_name
    )

    # Mock SecretSync GET
    mocked_responses.add(
        method=responses.GET,
        url=ss_endpoint,
        json=ss_record,
        status=200,
        content_type="application/json",
    )

    if remaining_count == 0:
        # Mock SecretSync DELETE
        mocked_responses.add(
            method=responses.DELETE,
            url=ss_endpoint,
            status=204,
            content_type="application/json",
        )
    else:
        # Mock SecretSync PUT (update with entry removed)
        ss_put = mocked_responses.add(
            method=responses.PUT,
            url=ss_endpoint,
            json=ss_record,
            status=200,
            content_type="application/json",
        )

    # Mock instance GET for ref-count check
    spc_resource_id = generate_resource_id(
        resource_group_name=resource_group_name,
        resource_provider="Microsoft.SecretSyncController",
        resource_path=f"/azureKeyVaultSecretProviderClasses/{spc_name}",
    )
    instance_record = get_mock_instance_record(
        name=instance_name,
        resource_group_name=resource_group_name,
        default_spc_resource_id=spc_resource_id,
    )
    instance_endpoint = get_instance_endpoint(
        resource_group_name=resource_group_name, instance_name=instance_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=instance_endpoint,
        json=instance_record,
        status=200,
        content_type="application/json",
    )

    # Mock custom location fetch (for get_associated_cl → get_resource_map)
    from .test_custom_locations_unit import (
        get_mock_custom_location_record,
    )

    cl_payload = get_mock_custom_location_record(
        name=generate_random_string(), resource_group_name=resource_group_name
    )
    # get_associated_cl uses resource_client.resources.get_by_id which GETs the extendedLocation URL
    cl_resource_id = instance_record["extendedLocation"]["name"]
    cl_url = f"{BASE_URL}{cl_resource_id}?api-version=2021-08-31-preview"
    mocked_responses.add(
        method=responses.GET,
        url=cl_url,
        json=cl_payload,
        status=200,
        content_type="application/json",
    )

    # Mock ARG query for all SecretSyncs in custom location (ref-count check)
    arg_secretsyncs = []
    if other_secretsyncs_reference:
        # Another SecretSync still references the same secret via the same SPC
        other_ss = get_mock_secretsync_record(
            name=generate_random_string(), resource_group_name=resource_group_name
        )
        other_ss["properties"]["objectSecretMapping"] = [
            {"sourcePath": secret_to_remove, "targetKey": "otherKey"}
        ]
        other_ss["properties"]["secretProviderClassName"] = spc_name
        arg_secretsyncs.append(other_ss)

    mocked_responses.add(
        method=responses.POST,
        url=ARG_ENDPOINT,
        json={"data": arg_secretsyncs},
        status=200,
        content_type="application/json",
    )

    # If not still referenced, mock SPC fetch + update
    if not other_secretsyncs_reference:
        spc_objects = (
            "array:\n    - |\n      objectName: secret1\n      objectType: secret\n"
            "    - |\n      objectName: secret2\n      objectType: secret\n"
        )

        spc_record = get_mock_spc_record(
            name=spc_name, resource_group_name=resource_group_name
        )
        spc_record["properties"]["keyvaultName"] = keyvault_name
        spc_record["properties"]["objects"] = spc_objects

        spc_endpoint = get_spc_endpoint(
            resource_group_name=resource_group_name, spc_name=spc_name
        )
        mocked_responses.add(
            method=responses.GET,
            url=spc_endpoint,
            json=spc_record,
            status=200,
            content_type="application/json",
        )

        # Mock SPC PUT
        spc_put = mocked_responses.add(
            method=responses.PUT,
            url=spc_endpoint,
            json=spc_record,
            status=200,
            content_type="application/json",
        )

    result = secretsync_secret_remove(
        cmd=mocked_cmd,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        secret_sync_name=secret_sync_name,
        secret_name=secret_to_remove,
        confirm_yes=True,
        wait_sec=0,
    )

    if remaining_count == 0:
        # Full deletion — returns None
        assert result is None
    else:
        # Partial removal — returns updated SecretSync resource
        assert result is not None
        # Verify the PUT body removed the secret
        ss_put_body = json.loads(ss_put.calls[0].request.body)
        remaining_mappings = ss_put_body["properties"]["objectSecretMapping"]
        assert len(remaining_mappings) == remaining_count
        assert all(m["sourcePath"] != secret_to_remove for m in remaining_mappings)

    if not other_secretsyncs_reference:
        # Verify SPC was updated to remove the objectName
        spc_put_body = json.loads(spc_put.calls[0].request.body)
        spc_objects_str = spc_put_body["properties"].get("objects", "")
        if spc_objects_str:
            assert secret_to_remove not in spc_objects_str


def test_secretsync_secret_remove_not_found(
    mocked_cmd,
    mocked_responses: responses,
):
    """Test that unsetting a nonexistent secret raises an error."""
    instance_name = generate_random_string()
    resource_group_name = generate_random_string()
    secret_sync_name = generate_random_string()

    ss_record = get_mock_secretsync_record(
        name=secret_sync_name, resource_group_name=resource_group_name
    )
    ss_endpoint = get_secretsync_endpoint(
        resource_group_name=resource_group_name, spc_name=secret_sync_name
    )
    mocked_responses.add(
        method=responses.GET,
        url=ss_endpoint,
        json=ss_record,
        status=200,
        content_type="application/json",
    )

    with pytest.raises(InvalidArgumentValueError, match="not found in SecretSync"):
        secretsync_secret_remove(
            cmd=mocked_cmd,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            secret_sync_name=secret_sync_name,
            secret_name="nonexistent_secret",
            confirm_yes=True,
            wait_sec=0,
        )
