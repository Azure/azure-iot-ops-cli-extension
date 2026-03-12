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
from .providers.orchestration.resources.connector_templates import ConnectorTemplates


def add_connector_opcua_trust(
    cmd,
    instance_name: str,
    resource_group: str,
    file: str,
    overwrite_secret: bool = False,
    secret_name: Optional[str] = None,
    expiration_date: Optional[str] = None,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).trust_add(
        file=file,
        secret_name=secret_name,
        overwrite_secret=overwrite_secret,
        expiration_date=expiration_date,
    )


def add_connector_opcua_issuer(
    cmd,
    instance_name: str,
    resource_group: str,
    file: str,
    overwrite_secret: bool = False,
    secret_name: Optional[str] = None,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).issuer_add(
        file=file,
        secret_name=secret_name,
        overwrite_secret=overwrite_secret,
    )


def add_connector_opcua_client(
    cmd,
    instance_name: str,
    resource_group: str,
    public_key_file: str,
    private_key_file: str,
    overwrite_secret: bool = False,
    subject_name: Optional[str] = None,
    application_uri: Optional[str] = None,
    public_key_secret_name: Optional[str] = None,
    private_key_secret_name: Optional[str] = None,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).client_add(
        public_key_file=public_key_file,
        private_key_file=private_key_file,
        subject_name=subject_name,
        application_uri=application_uri,
        public_key_secret_name=public_key_secret_name,
        private_key_secret_name=private_key_secret_name,
        overwrite_secret=overwrite_secret,
    )


def remove_connector_opcua_trust(
    cmd,
    instance_name: str,
    resource_group: str,
    certificate_names: List[str],
    confirm_yes: Optional[bool] = False,
    force: Optional[bool] = False,
    include_secrets: Optional[bool] = False,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).remove(
        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
        certificate_names=certificate_names,
        confirm_yes=confirm_yes,
        force=force,
        include_secrets=include_secrets,
    )


def remove_connector_opcua_issuer(
    cmd,
    instance_name: str,
    resource_group: str,
    certificate_names: List[str],
    confirm_yes: Optional[bool] = False,
    force: Optional[bool] = False,
    include_secrets: Optional[bool] = False,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).remove(
        secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
        certificate_names=certificate_names,
        confirm_yes=confirm_yes,
        force=force,
        include_secrets=include_secrets,
    )


def remove_connector_opcua_client(
    cmd,
    instance_name: str,
    resource_group: str,
    certificate_names: List[str],
    confirm_yes: Optional[bool] = False,
    force: Optional[bool] = False,
    include_secrets: Optional[bool] = False,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).remove(
        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
        certificate_names=certificate_names,
        confirm_yes=confirm_yes,
        force=force,
        include_secrets=include_secrets,
    )


def show_connector_opcua_trust(
    cmd,
    instance_name: str,
    resource_group: str,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).show(
        secretsync_name=OPCUA_TRUST_LIST_SECRET_SYNC_NAME,
    )


def show_connector_opcua_issuer(
    cmd,
    instance_name: str,
    resource_group: str,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).show(
        secretsync_name=OPCUA_ISSUER_LIST_SECRET_SYNC_NAME,
    )


def show_connector_opcua_client(
    cmd,
    instance_name: str,
    resource_group: str,
) -> dict:
    return OpcUACerts(
        cmd,
        resource_group_name=resource_group,
        instance_name=instance_name,
    ).show(
        secretsync_name=OPCUA_CLIENT_CERT_SECRET_SYNC_NAME,
    )


# Connector Template Commands
def create_connector_template(
    cmd,
    name: str,
    resource_group: str,
    instance: str,
    connector_metadata_ref: str,
    replicas: Optional[int] = None,
    log_level: Optional[str] = None,
    image_pull_policy: Optional[str] = None,
    image_pull_secrets: Optional[List[str]] = None,
    allocation_policy: Optional[str] = None,
    bucket_size: Optional[int] = None,
    secrets: Optional[List[str]] = None,
    storage_volumes: Optional[List[str]] = None,
    connector_config: Optional[List[str]] = None,
    trust_settings_secret_ref: Optional[str] = None,
) -> dict:
    return ConnectorTemplates(cmd).create(
        template_name=name,
        resource_group_name=resource_group,
        instance_name=instance,
        connector_metadata_ref=connector_metadata_ref,
        replicas=replicas,
        log_level=log_level,
        image_pull_policy=image_pull_policy,
        image_pull_secrets=image_pull_secrets,
        allocation_policy=allocation_policy,
        bucket_size=bucket_size,
        secrets=secrets,
        storage_volumes=storage_volumes,
        connector_config=connector_config,
        trust_settings_secret_ref=trust_settings_secret_ref,
    )


def update_connector_template(
    cmd,
    name: str,
    resource_group: str,
    instance: str,
    connector_metadata_ref: Optional[str] = None,
    replicas: Optional[int] = None,
    log_level: Optional[str] = None,
    image_pull_policy: Optional[str] = None,
    image_pull_secrets: Optional[List[str]] = None,
    allocation_policy: Optional[str] = None,
    bucket_size: Optional[int] = None,
    secrets: Optional[List[str]] = None,
    storage_volumes: Optional[List[str]] = None,
    connector_config: Optional[List[str]] = None,
    trust_settings_secret_ref: Optional[str] = None,
) -> dict:
    return ConnectorTemplates(cmd).update(
        template_name=name,
        resource_group_name=resource_group,
        instance_name=instance,
        connector_metadata_ref=connector_metadata_ref,
        replicas=replicas,
        log_level=log_level,
        image_pull_policy=image_pull_policy,
        image_pull_secrets=image_pull_secrets,
        allocation_policy=allocation_policy,
        bucket_size=bucket_size,
        secrets=secrets,
        storage_volumes=storage_volumes,
        connector_config=connector_config,
        trust_settings_secret_ref=trust_settings_secret_ref,
    )


def show_connector_template(
    cmd,
    name: str,
    resource_group: str,
    instance: str,
) -> dict:
    return ConnectorTemplates(cmd).show(
        template_name=name,
        resource_group_name=resource_group,
        instance_name=instance,
    )


def delete_connector_template(
    cmd,
    name: str,
    resource_group: str,
    instance: str,
    confirm_yes: Optional[bool] = False,
) -> dict:
    return ConnectorTemplates(cmd).delete(
        template_name=name,
        resource_group_name=resource_group,
        instance_name=instance,
        confirm_yes=confirm_yes,
    )


def list_connector_templates(
    cmd,
    resource_group: str,
    instance: str,
) -> List[dict]:
    return ConnectorTemplates(cmd).list(
        resource_group_name=resource_group,
        instance_name=instance,
    )
