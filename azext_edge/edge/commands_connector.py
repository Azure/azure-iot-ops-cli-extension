# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from .providers.orchestration.resources.connector.opcua.certs import OpcUACerts


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
