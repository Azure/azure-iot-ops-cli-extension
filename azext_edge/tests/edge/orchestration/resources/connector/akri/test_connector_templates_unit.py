# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import io
import json
import os
import tarfile
from typing import Optional

import pytest
from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.providers.orchestration.resources.connector_templates import (
    ConnectorTemplates,
)

from ......generators import generate_random_string
from ...conftest import (
    INSTANCES_API_VERSION,
    RESOURCE_PROVIDER,
    get_base_endpoint,
    get_mock_resource,
)


def get_connector_template_endpoint(
    instance_name: str, resource_group_name: Optional[str] = None, template_name: Optional[str] = None,
    api_version: str = INSTANCES_API_VERSION,
) -> str:
    resource_path = f"/instances/{instance_name}/akriConnectorTemplates"
    if template_name:
        resource_path += f"/{template_name}"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider=RESOURCE_PROVIDER,
        api_version=api_version,
    )


def get_mock_connector_template_record(
    name: str,
    instance_name: str,
    resource_group_name: str,
    location: Optional[str] = None,
    cl_name: Optional[str] = None,
) -> dict:
    optional_kwargs = {}
    if cl_name:
        optional_kwargs["custom_location_name"] = cl_name
    record = get_mock_resource(
        name=name,
        resource_provider=RESOURCE_PROVIDER,
        resource_path=f"/instances/{instance_name}/akriConnectorTemplates/{name}",
        location=location,
        properties={
            "aioMetadata": {},
            "diagnostics": {"logs": {"level": "info"}},
            "deviceInboundEndpointTypes": [
                {
                    "configurationSchemaRefs": {
                        "additionalConfigSchemaRef": "aio-sr://target4/microsoft-onvif-7722a864:1",
                        "defaultEventsConfigSchemaRef": "aio-sr://target4/microsoft-onvif-51b86567:1",
                        "defaultProcessControlConfigSchemaRef": "aio-sr://target4/microsoft-onvif-52de1fd3:1",
                    },
                    "endpointType": "Microsoft.Onvif",
                }
            ],
            "runtimeConfiguration": {
                "runtimeConfigurationType": "ManagedConfiguration",
                "managedConfigurationSettings": {
                    "managedConfigurationType": "ImageConfiguration",
                    "imageConfigurationSettings": {
                        "imageName": "aio-connectors/onvif-connector",
                        "imagePullPolicy": "Never",
                        "replicas": 2,
                        "registrySettings": {
                            "registrySettingsType": "ContainerRegistry",
                            "containerRegistrySettings": {
                                "registry": "mcr.microsoft.com",
                                "imagePullSecrets": [{"secretRef": "abcde"}],
                            },
                        },
                        "tagDigestSettings": {"tagDigestType": "Tag", "tag": "1.2.12"},
                    },
                    "allocation": {"policy": "Bucketized", "bucketSize": 1},
                    "additionalConfiguration": {"key1": "value1"},
                },
            },
        },
        resource_group_name=resource_group_name,
        qualified_type=f"{RESOURCE_PROVIDER}/instances/akriConnectorTemplates",
        is_proxy_resource=True,
        **optional_kwargs,
    )
    return record


def _provider() -> ConnectorTemplates:
    # Bypass __init__ (which requires a command context) since the extraction
    # helpers under test do not rely on any instance state.
    return object.__new__(ConnectorTemplates)


def _file_member(name: str, data: bytes) -> tuple:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    return info, data


def _build_tar_blob(members: list, gzip: bool = True) -> bytes:
    """Build a tar(.gz) blob from a list of (TarInfo, data) members."""
    buffer = io.BytesIO()
    mode = "w:gz" if gzip else "w"
    with tarfile.open(fileobj=buffer, mode=mode) as tar:
        for info, data in members:
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    return buffer.getvalue()


@pytest.mark.parametrize("gzip", [True, False])
def test_safe_extract_valid_archive(gzip, tmp_path):
    connector_name = generate_random_string()
    payload = json.dumps({"name": connector_name}).encode("utf-8")
    blob = _build_tar_blob([_file_member("connector-metadata.json", payload)], gzip=gzip)

    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz" if gzip else "r") as tar:
        _provider()._safe_extractall(tar, str(tmp_path))

    extracted = tmp_path / "connector-metadata.json"
    assert extracted.exists()
    assert json.loads(extracted.read_text())["name"] == connector_name


@pytest.mark.parametrize(
    "malicious_name",
    [
        "../malicious.txt",
        "../../malicious.txt",
        "foo/../../malicious.txt",
    ],
)
def test_safe_extract_blocks_relative_traversal(malicious_name, tmp_path):
    blob = _build_tar_blob([_file_member(malicious_name, generate_random_string().encode("utf-8"))])

    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        with pytest.raises(ValidationError):
            _provider()._safe_extractall(tar, str(tmp_path))

    # Ensure nothing was written outside the destination directory.
    outside_path = os.path.realpath(os.path.join(str(tmp_path), malicious_name))
    assert not os.path.exists(outside_path)


def test_safe_extract_blocks_absolute_path(tmp_path):
    # An absolute member name escapes the destination via os.path.join and must be rejected.
    marker = str(tmp_path.parent / f"{generate_random_string()}.txt")
    assert not os.path.exists(marker)
    blob = _build_tar_blob([_file_member(marker, generate_random_string().encode("utf-8"))])

    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        with pytest.raises(ValidationError):
            _provider()._safe_extractall(tar, str(tmp_path))

    assert not os.path.exists(marker)


@pytest.mark.parametrize(
    "member_type",
    [
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
        tarfile.FIFOTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
    ],
)
def test_safe_extract_blocks_unsupported_members(member_type, tmp_path):
    member = tarfile.TarInfo(name="connector-metadata.json")
    member.type = member_type
    if member_type in (tarfile.SYMTYPE, tarfile.LNKTYPE):
        member.linkname = "../../etc/passwd"
    blob = _build_tar_blob([(member, None)])

    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        with pytest.raises(ValidationError):
            _provider()._safe_extractall(tar, str(tmp_path))


def test_is_within_directory(tmp_path):
    inside = os.path.join(str(tmp_path), "sub", "file.txt")
    outside = os.path.join(str(tmp_path), "..", "file.txt")

    assert _provider()._is_within_directory(str(tmp_path), inside) is True
    assert _provider()._is_within_directory(str(tmp_path), outside) is False
