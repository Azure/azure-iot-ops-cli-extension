# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional
from .providers.orchestration.resources.connector.opcua.certs import (
    OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
    OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
    OpcUACerts,
)


def add_connector_opcua_trust(
    cmd,
    instance_name: str,
    resource_group: str,
    file: str,
    secret_name: Optional[str] = None,
) -> dict:
    return OpcUACerts(cmd).trust_add(
        instance_name=instance_name,
        resource_group=resource_group,
        file=file,
        secret_name=secret_name,
    )


def add_connector_opcua_issuer(
    cmd,
    instance_name: str,
    resource_group: str,
    file: str,
    secret_name: Optional[str] = None,
) -> dict:
    return OpcUACerts(cmd).issuer_add(
        instance_name=instance_name,
        resource_group=resource_group,
        file=file,
        secret_name=secret_name,
    )


def add_connector_opcua_client(
    cmd,
    instance_name: str,
    resource_group: str,
    public_key_file: str,
    private_key_file: str,
    subject_name: str,
    application_uri: str,
    public_key_secret_name: Optional[str] = None,
    private_key_secret_name: Optional[str] = None,
) -> dict:
    return OpcUACerts(cmd).client_add(
        instance_name=instance_name,
        resource_group=resource_group,
        public_key_file=public_key_file,
        private_key_file=private_key_file,
        subject_name=subject_name,
        application_uri=application_uri,
        public_key_secret_name=public_key_secret_name,
        private_key_secret_name=private_key_secret_name,
    )


def remove_connector_opcua_trust(
    cmd,
    instance_name: str,
    resource_group: str,
    certificate_names: List[str],
    force: Optional[bool] = False,
    include_secrets: Optional[bool] = False,
) -> dict:
    return OpcUACerts(cmd).remove(
        instance_name=instance_name,
        resource_group=resource_group,
        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
        certificate_names=certificate_names,
        force=force,
        include_secrets=include_secrets,
    )


def remove_connector_opcua_issuer(
    cmd,
    instance_name: str,
    resource_group: str,
    certificate_names: List[str],
    force: Optional[bool] = False,
    include_secrets: Optional[bool] = False,
) -> dict:
    return OpcUACerts(cmd).remove(
        instance_name=instance_name,
        resource_group=resource_group,
        secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
        certificate_names=certificate_names,
        force=force,
        include_secrets=include_secrets,
    )


def remove_connector_opcua_client(
    cmd,
    instance_name: str,
    resource_group: str,
    certificate_names: List[str],
    force: Optional[bool] = False,
    include_secrets: Optional[bool] = False,
) -> dict:
    return OpcUACerts(cmd).remove(
        instance_name=instance_name,
        resource_group=resource_group,
        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
        certificate_names=certificate_names,
        force=force,
        include_secrets=include_secrets,
    )


def show_connector_opcua_trust(
    cmd,
    instance_name: str,
    resource_group: str,
) -> dict:
    return OpcUACerts(cmd).show(
        instance_name=instance_name,
        resource_group=resource_group,
        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
    )


def show_connector_opcua_issuer(
    cmd,
    instance_name: str,
    resource_group: str,
) -> dict:
    return OpcUACerts(cmd).show(
        instance_name=instance_name,
        resource_group=resource_group,
        secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
    )


def show_connector_opcua_client(
    cmd,
    instance_name: str,
    resource_group: str,
) -> dict:
    return OpcUACerts(cmd).show(
        instance_name=instance_name,
        resource_group=resource_group,
        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    )
