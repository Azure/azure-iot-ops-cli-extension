# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional

from azext_edge.edge.providers.orchestration.common import DataflowEndpointAuthenticationType, DataflowEndpointFabricPathType, DataflowEndpointType

from .providers.orchestration.resources import DataFlowEndpoints, DataFlowProfiles


def show_dataflow_profile(cmd, profile_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowProfiles(cmd).show(
        name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflow_profiles(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowProfiles(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)


def show_dataflow(cmd, dataflow_name: str, profile_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowProfiles(cmd).dataflows.show(
        name=dataflow_name,
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflows(cmd, profile_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowProfiles(cmd).dataflows.list(
        dataflow_profile_name=profile_name, instance_name=instance_name, resource_group_name=resource_group_name
    )


def create_dataflow_endpoint_adx(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    authentication_method: str,
    database_name: str,
    host: str,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    batching_latency: Optional[int] = None,
    message_count: Optional[int] = None,
) -> dict:
    kwargs = {
        "authentication_method": authentication_method,
        "database_name": database_name,
        "host": host,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "audience": audience,
        "batching_latency": batching_latency,
        "message_count": message_count,
    }

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.DATAEXPLORER.value,
        **kwargs
    )


def create_dataflow_endpoint_adls(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    authentication_method: str,
    host: str,
    secret_name: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    batching_latency: Optional[int] = None,
    message_count: Optional[int] = None,
) -> dict:
    kwargs = {
        "authentication_method": authentication_method,
        "host": host,
        "secret_name": secret_name,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "audience": audience,
        "batching_latency": batching_latency,
        "message_count": message_count,
    }

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.DATALAKESTORAGE.value,
        **kwargs
    )

def create_dataflow_endpoint_fabric(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    authentication_method: str,
    lakehouse_name: str,
    workspace_name: str,
    path_type: str,
    host: str,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    batching_latency: Optional[int] = None,
    message_count: Optional[int] = None,
) -> dict:
    
    kwargs = {
        "authentication_method": authentication_method,
        "lakehouse_name": lakehouse_name,
        "workspace_name": workspace_name,
        "path_type": path_type,
        "host": host,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "scope": scope,
        "audience": audience,
        "batching_latency": batching_latency,
        "message_count": message_count,
    }

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.FABRICONELAKE.value,
        **kwargs
    )


def create_dataflow_endpoint_kafka(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    authentication_method: str,
    host: str,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sasl_type: Optional[str] = None,
    sasl_secret_name: Optional[str] = None,
    x509_secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    group_id: Optional[str] = None,
    batching_disabled: Optional[bool] = None,
    batching_latency: Optional[int] = None,
    message_count: Optional[int] = None,
    max_byte: Optional[int] = None,
    copy_disabled: Optional[bool] = None,
    compression: Optional[str] = None,
    acks: Optional[str] = None,
    partition_strategy: Optional[str] = None,
    tls_disabled: Optional[bool] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: Optional[str] = None,
) -> dict:
    kwargs = {
        "authentication_method": authentication_method,
        "host": host,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "sasl_type": sasl_type,
        "sasl_secret_name": sasl_secret_name,
        "x509_secret_name": x509_secret_name,
        "scope": scope,
        "audience": audience,
        "group_id": group_id,
        "batching_disabled": batching_disabled,
        "batching_latency": batching_latency,
        "message_count": message_count,
        "max_byte": max_byte,
        "copy_disabled": copy_disabled,
        "compression": compression,
        "acks": acks,
        "partition_strategy": partition_strategy,
        "tls_disabled": tls_disabled,
        "config_map_reference": config_map_reference,
        "cloud_event_attribute": cloud_event_attribute
    }

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.KAFKA.value,
        **kwargs
    )


def create_dataflow_endpoint_localstorage(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    pvc_reference: str,
) -> dict:
    kwargs = {
        "pvc_reference": pvc_reference,
    }

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.LOCALSTORAGE.value,
        **kwargs
    )


def create_dataflow_endpoint_mqtt(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    authentication_method: str,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sas_audience: Optional[str] = None,
    x509_secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    sa_audience: Optional[str] = None,
    host: Optional[str] = None,
    client_id_prefix: Optional[str] = None,
    protocol: Optional[str] = None,
    keep_alive: Optional[int] = None,
    retain: Optional[str] = None,
    max_inflight_messages: Optional[int] = None,
    qos: Optional[int] = None,
    session_expiry: Optional[int] = None,
    tls_disabled: Optional[bool] = None,
    cloud_event_attribute: Optional[str] = None,
) -> dict:
    # TODO: Since we are building up mapping, use the name in api directly
    kwargs = {
        "authentication_method": authentication_method,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "sas_audience": sas_audience,
        "x509_secret_name": x509_secret_name,
        "scope": scope,
        "sa_audience": sa_audience,
        "host": host,
        "client_id_prefix": client_id_prefix,
        "protocol": protocol,
        "keep_alive": keep_alive,
        "retain": retain,
        "max_inflight_messages": max_inflight_messages,
        "qos": qos,
        "session_expiry": session_expiry,
        "tls_disabled": tls_disabled,
        "cloud_event_attribute": cloud_event_attribute
    }

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.MQTT.value,
        **kwargs
    )


def show_dataflow_endpoint(cmd, endpoint_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowEndpoints(cmd).show(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflow_endpoints(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowEndpoints(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)
