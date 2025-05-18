# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Iterable, Optional

from .providers.orchestration.common import (
    AIO_MQTT_DEFAULT_CONFIG_MAP,
    DataflowEndpointKafkaAcksType,
    DataflowEndpointType,
    KafkaCloudEventAttributeType,
    KafkaCompressionType,
    KafkaPartitionStrategyType,
    ListenerProtocol,
    MqttRetainType,
)
from .providers.orchestration.resources import DataFlowEndpoints, DataFlowProfiles
from .common import DEFAULT_DATAFLOW_PROFILE


def create_dataflow_profile(
    cmd,
    profile_name: str,
    instance_name: str,
    resource_group_name: str,
    profile_instances: int = 1,
    log_level: str = "info",
    **kwargs,
) -> dict:
    return DataFlowProfiles(cmd).create(
        name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        profile_instances=profile_instances,
        log_level=log_level,
        **kwargs,
    )


def update_dataflow_profile(
    cmd,
    profile_name: str,
    instance_name: str,
    resource_group_name: str,
    profile_instances: Optional[int] = None,
    log_level: Optional[str] = None,
    **kwargs,
) -> dict:
    return DataFlowProfiles(cmd).update(
        name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        profile_instances=profile_instances,
        log_level=log_level,
        **kwargs,
    )


def delete_dataflow_profile(
    cmd,
    profile_name: str,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: Optional[bool] = None,
    **kwargs,
):
    return DataFlowProfiles(cmd).delete(
        name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )


def show_dataflow_profile(cmd, profile_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowProfiles(cmd).show(
        name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflow_profiles(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowProfiles(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)


def show_dataflow(
    cmd,
    dataflow_name: str,
    instance_name: str,
    resource_group_name: str,
    profile_name: str = DEFAULT_DATAFLOW_PROFILE,
) -> dict:
    return DataFlowProfiles(cmd).dataflows.show(
        name=dataflow_name,
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflows(
    cmd,
    instance_name: str,
    resource_group_name: str,
    profile_name: str = DEFAULT_DATAFLOW_PROFILE,
) -> Iterable[dict]:
    return DataFlowProfiles(cmd).dataflows.list(
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def apply_dataflow(
    cmd,
    dataflow_name: str,
    instance_name: str,
    resource_group_name: str,
    config_file: str,
    profile_name: str = DEFAULT_DATAFLOW_PROFILE,
    **kwargs: dict,
) -> dict:
    return DataFlowProfiles(cmd).dataflows.apply(
        name=dataflow_name,
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file=config_file,
        **kwargs,
    )


def delete_dataflow(
    cmd,
    dataflow_name: str,
    instance_name: str,
    resource_group_name: str,
    profile_name: str = DEFAULT_DATAFLOW_PROFILE,
    confirm_yes: Optional[bool] = None,
    **kwargs: dict,
):
    return DataFlowProfiles(cmd).dataflows.delete(
        name=dataflow_name,
        dataflow_profile_name=profile_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )


def apply_dataflow_endpoint(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    config_file: str,
    **kwargs,
) -> dict:
    return DataFlowEndpoints(cmd).apply(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        config_file=config_file,
        **kwargs,
    )


def delete_dataflow_endpoint(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    confirm_yes: bool = False,
    **kwargs,
):
    return DataFlowEndpoints(cmd).delete(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        confirm_yes=confirm_yes,
        **kwargs,
    )


def create_dataflow_endpoint_adx(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    database_name: str,
    host: str,
    latency: int = 60,
    message_count: int = 100000,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.DATAEXPLORER.value,
        database_name=database_name,
        host=host,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        sami_audience=audience,
        latency=latency,
        message_count=message_count,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def create_dataflow_endpoint_adls(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    storage_account_name: str,
    latency: int = 60,
    message_count: int = 100000,
    secret_name: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.DATALAKESTORAGE.value,
        storage_account_name=storage_account_name,
        at_secret_name=secret_name,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        sami_audience=audience,
        latency=latency,
        message_count=message_count,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def create_dataflow_endpoint_fabric_onelake(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    lakehouse_name: str,
    workspace_name: str,
    path_type: str,
    latency: int = 60,
    message_count: int = 100000,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.FABRICONELAKE.value,
        lakehouse_name=lakehouse_name,
        workspace_name=workspace_name,
        path_type=path_type,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        sami_audience=audience,
        latency=latency,
        message_count=message_count,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def create_dataflow_endpoint_eventhub(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    eventhub_namespace: str,
    latency: int = 5,
    max_byte: int = 1000000,
    message_count: int = 100000,
    batching_disabled: bool = False,
    copy_broker_props_disabled: bool = False,
    acks: str = DataflowEndpointKafkaAcksType.ALL.value,
    compression: str = KafkaCompressionType.NONE.value,
    partition_strategy: str = KafkaPartitionStrategyType.DEFAULT.value,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sasl_type: Optional[str] = None,
    secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    group_id: Optional[str] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: str = KafkaCloudEventAttributeType.PROPAGATE.value,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.EVENTHUB.value,
        eventhub_namespace=eventhub_namespace,
        client_id=client_id,
        tenant_id=tenant_id,
        sasl_type=sasl_type,
        sasl_secret_name=secret_name,
        scope=scope,
        sami_audience=audience,
        group_id=group_id,
        batching_disabled=batching_disabled,
        latency_ms=latency,
        message_count=message_count,
        max_byte=max_byte,
        copy_broker_props_disabled=copy_broker_props_disabled,
        compression=compression,
        acks=acks,
        partition_strategy=partition_strategy,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def create_dataflow_endpoint_fabric_realtime(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    host: str,
    latency: int = 5,
    max_byte: int = 1000000,
    message_count: int = 100000,
    tls_disabled: bool = False,
    batching_disabled: bool = False,
    copy_broker_props_disabled: bool = False,
    acks: str = DataflowEndpointKafkaAcksType.ALL.value,
    compression: str = KafkaCompressionType.NONE.value,
    partition_strategy: str = KafkaPartitionStrategyType.DEFAULT.value,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sasl_type: Optional[str] = None,
    scope: Optional[str] = None,
    secret_name: Optional[str] = None,
    audience: Optional[str] = None,
    group_id: Optional[str] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: str = KafkaCloudEventAttributeType.PROPAGATE.value,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.FABRICREALTIME.value,
        host=host,
        sasl_type=sasl_type,
        sasl_secret_name=secret_name,
        group_id=group_id,
        batching_disabled=batching_disabled,
        latency_ms=latency,
        message_count=message_count,
        max_byte=max_byte,
        copy_broker_props_disabled=copy_broker_props_disabled,
        compression=compression,
        acks=acks,
        partition_strategy=partition_strategy,
        tls_disabled=tls_disabled,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        authentication_type=authentication_type,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        sami_audience=audience,
        show_config=show_config,
    )


def create_dataflow_endpoint_custom_kafka(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    hostname: str,
    port: int,
    latency: int = 5,
    max_byte: int = 1000000,
    message_count: int = 100000,
    tls_disabled: bool = False,
    batching_disabled: bool = False,
    no_auth: bool = False,
    copy_broker_props_disabled: bool = False,
    acks: str = DataflowEndpointKafkaAcksType.ALL.value,
    compression: str = KafkaCompressionType.NONE.value,
    partition_strategy: str = KafkaPartitionStrategyType.DEFAULT.value,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sasl_type: Optional[str] = None,
    secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    group_id: Optional[str] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: str = KafkaCloudEventAttributeType.PROPAGATE.value,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.CUSTOMKAFKA.value,
        hostname=hostname,
        port=port,
        client_id=client_id,
        tenant_id=tenant_id,
        sasl_type=sasl_type,
        sasl_secret_name=secret_name,
        scope=scope,
        sami_audience=audience,
        group_id=group_id,
        batching_disabled=batching_disabled,
        latency_ms=latency,
        message_count=message_count,
        max_byte=max_byte,
        copy_broker_props_disabled=copy_broker_props_disabled,
        compression=compression,
        acks=acks,
        partition_strategy=partition_strategy,
        tls_disabled=tls_disabled,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        no_auth=no_auth,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def create_dataflow_endpoint_localstorage(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    pvc_reference: str,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.LOCALSTORAGE.value,
        pvc_reference=pvc_reference,
        show_config=show_config,
    )


def create_dataflow_endpoint_aio(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    hostname: str,
    port: int,
    keep_alive: int = 60,
    max_inflight_messages: int = 100,
    qos: int = 1,
    session_expiry: int = 3600,
    tls_disabled: bool = False,
    no_auth: bool = False,
    config_map_reference: str = AIO_MQTT_DEFAULT_CONFIG_MAP,
    secret_name: Optional[str] = None,
    audience: Optional[str] = None,
    client_id_prefix: Optional[str] = None,
    protocol: str = ListenerProtocol.MQTT.value,
    retain: str = MqttRetainType.KEEP.value,
    cloud_event_attribute: str = KafkaCloudEventAttributeType.PROPAGATE.value,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.AIOLOCALMQTT.value,
        x509_secret_name=secret_name,
        sat_audience=audience,
        hostname=hostname,
        port=port,
        client_id_prefix=client_id_prefix,
        protocol=protocol,
        keep_alive=keep_alive,
        retain=retain,
        max_inflight_messages=max_inflight_messages,
        qos=qos,
        session_expiry=session_expiry,
        tls_disabled=tls_disabled,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        no_auth=no_auth,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def create_dataflow_endpoint_eventgrid(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    hostname: str,
    port: int,
    keep_alive: int = 60,
    max_inflight_messages: int = 100,
    qos: int = 1,
    session_expiry: int = 3600,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    audience: Optional[str] = None,
    secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    client_id_prefix: Optional[str] = None,
    protocol: str = ListenerProtocol.MQTT.value,
    retain: str = MqttRetainType.KEEP.value,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: str = KafkaCloudEventAttributeType.PROPAGATE.value,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.EVENTGRID.value,
        client_id=client_id,
        tenant_id=tenant_id,
        sami_audience=audience,
        x509_secret_name=secret_name,
        scope=scope,
        hostname=hostname,
        port=port,
        client_id_prefix=client_id_prefix,
        protocol=protocol,
        keep_alive=keep_alive,
        retain=retain,
        max_inflight_messages=max_inflight_messages,
        qos=qos,
        session_expiry=session_expiry,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def create_dataflow_endpoint_custom_mqtt(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    hostname: str,
    port: int,
    keep_alive: int = 60,
    max_inflight_messages: int = 100,
    qos: int = 1,
    session_expiry: int = 3600,
    tls_disabled: bool = False,
    no_auth: bool = False,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sami_audience: Optional[str] = None,
    secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    sat_audience: Optional[str] = None,
    client_id_prefix: Optional[str] = None,
    protocol: str = ListenerProtocol.MQTT.value,
    retain: str = MqttRetainType.KEEP.value,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: str = KafkaCloudEventAttributeType.PROPAGATE.value,
    authentication_type: Optional[str] = None,
    show_config: Optional[str] = None,
) -> dict:

    return DataFlowEndpoints(cmd).create(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.CUSTOMMQTT.value,
        client_id=client_id,
        tenant_id=tenant_id,
        sami_audience=sami_audience,
        x509_secret_name=secret_name,
        scope=scope,
        sat_audience=sat_audience,
        hostname=hostname,
        port=port,
        client_id_prefix=client_id_prefix,
        protocol=protocol,
        keep_alive=keep_alive,
        retain=retain,
        max_inflight_messages=max_inflight_messages,
        qos=qos,
        session_expiry=session_expiry,
        tls_disabled=tls_disabled,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        no_auth=no_auth,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def update_dataflow_endpoint_adx(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    latency: Optional[int] = None,
    message_count: Optional[int] = None,
    database_name: Optional[str] = None,
    host: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.DATAEXPLORER.value,
        database_name=database_name,
        host=host,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        sami_audience=audience,
        latency=latency,
        message_count=message_count,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def update_dataflow_endpoint_adls(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    storage_account_name: Optional[str] = None,
    latency: Optional[int] = None,
    message_count: Optional[int] = None,
    secret_name: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.DATALAKESTORAGE.value,
        storage_account_name=storage_account_name,
        at_secret_name=secret_name,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        sami_audience=audience,
        latency=latency,
        message_count=message_count,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def update_dataflow_endpoint_fabric_onelake(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    lakehouse_name: Optional[str] = None,
    workspace_name: Optional[str] = None,
    path_type: Optional[str] = None,
    latency: Optional[int] = None,
    message_count: Optional[int] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.FABRICONELAKE.value,
        lakehouse_name=lakehouse_name,
        workspace_name=workspace_name,
        path_type=path_type,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        sami_audience=audience,
        latency=latency,
        message_count=message_count,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def update_dataflow_endpoint_eventhub(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    eventhub_namespace: Optional[str] = None,
    latency: Optional[int] = None,
    max_byte: Optional[int] = None,
    message_count: Optional[int] = None,
    batching_disabled: Optional[bool] = None,
    copy_broker_props_disabled: Optional[bool] = None,
    acks: Optional[str] = None,
    compression: Optional[str] = None,
    partition_strategy: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sasl_type: Optional[str] = None,
    secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    group_id: Optional[str] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.EVENTHUB.value,
        eventhub_namespace=eventhub_namespace,
        client_id=client_id,
        tenant_id=tenant_id,
        sasl_type=sasl_type,
        sasl_secret_name=secret_name,
        scope=scope,
        sami_audience=audience,
        group_id=group_id,
        batching_disabled=batching_disabled,
        latency_ms=latency,
        message_count=message_count,
        max_byte=max_byte,
        copy_broker_props_disabled=copy_broker_props_disabled,
        compression=compression,
        acks=acks,
        partition_strategy=partition_strategy,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def update_dataflow_endpoint_fabric_realtime(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    host: Optional[str] = None,
    latency: Optional[int] = None,
    max_byte: Optional[int] = None,
    message_count: Optional[int] = None,
    tls_disabled: Optional[bool] = None,
    batching_disabled: Optional[bool] = None,
    copy_broker_props_disabled: Optional[bool] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    acks: Optional[str] = None,
    compression: Optional[str] = None,
    partition_strategy: Optional[str] = None,
    sasl_type: Optional[str] = None,
    secret_name: Optional[str] = None,
    group_id: Optional[str] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.FABRICREALTIME.value,
        host=host,
        sasl_type=sasl_type,
        sasl_secret_name=secret_name,
        group_id=group_id,
        batching_disabled=batching_disabled,
        latency_ms=latency,
        message_count=message_count,
        max_byte=max_byte,
        copy_broker_props_disabled=copy_broker_props_disabled,
        compression=compression,
        acks=acks,
        partition_strategy=partition_strategy,
        tls_disabled=tls_disabled,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        authentication_type=authentication_type,
        client_id=client_id,
        tenant_id=tenant_id,
        scope=scope,
        sami_audience=audience,
        show_config=show_config,
    )


def update_dataflow_endpoint_custom_kafka(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    hostname: Optional[str] = None,
    port: Optional[int] = None,
    latency: Optional[int] = None,
    max_byte: Optional[int] = None,
    message_count: Optional[int] = None,
    tls_disabled: Optional[bool] = None,
    batching_disabled: Optional[bool] = None,
    no_auth: Optional[bool] = None,
    copy_broker_props_disabled: Optional[bool] = None,
    acks: Optional[str] = None,
    compression: Optional[str] = None,
    partition_strategy: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sasl_type: Optional[str] = None,
    secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    audience: Optional[str] = None,
    group_id: Optional[str] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.CUSTOMKAFKA.value,
        hostname=hostname,
        port=port,
        client_id=client_id,
        tenant_id=tenant_id,
        sasl_type=sasl_type,
        sasl_secret_name=secret_name,
        scope=scope,
        sami_audience=audience,
        group_id=group_id,
        batching_disabled=batching_disabled,
        latency_ms=latency,
        message_count=message_count,
        max_byte=max_byte,
        copy_broker_props_disabled=copy_broker_props_disabled,
        compression=compression,
        acks=acks,
        partition_strategy=partition_strategy,
        tls_disabled=tls_disabled,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        no_auth=no_auth,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def update_dataflow_endpoint_localstorage(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    pvc_reference: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.LOCALSTORAGE.value,
        pvc_reference=pvc_reference,
        show_config=show_config,
    )


def update_dataflow_endpoint_aio(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    hostname: Optional[str] = None,
    port: Optional[int] = None,
    keep_alive: Optional[int] = None,
    max_inflight_messages: Optional[int] = None,
    qos: Optional[int] = None,
    tls_disabled: bool = False,
    secret_name: Optional[str] = None,
    audience: Optional[str] = None,
    client_id_prefix: Optional[str] = None,
    protocol: Optional[str] = None,
    retain: Optional[str] = None,
    session_expiry: Optional[int] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: Optional[str] = None,
    no_auth: Optional[bool] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.AIOLOCALMQTT.value,
        x509_secret_name=secret_name,
        sat_audience=audience,
        hostname=hostname,
        port=port,
        client_id_prefix=client_id_prefix,
        protocol=protocol,
        keep_alive=keep_alive,
        retain=retain,
        max_inflight_messages=max_inflight_messages,
        qos=qos,
        session_expiry=session_expiry,
        tls_disabled=tls_disabled,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        no_auth=no_auth,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def update_dataflow_endpoint_eventgrid(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    hostname: Optional[str] = None,
    port: Optional[int] = None,
    keep_alive: Optional[int] = None,
    max_inflight_messages: Optional[int] = None,
    qos: Optional[int] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    audience: Optional[str] = None,
    secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    client_id_prefix: Optional[str] = None,
    protocol: Optional[str] = None,
    retain: Optional[str] = None,
    session_expiry: Optional[int] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.EVENTGRID.value,
        client_id=client_id,
        tenant_id=tenant_id,
        sat_audience=audience,
        x509_secret_name=secret_name,
        scope=scope,
        hostname=hostname,
        port=port,
        client_id_prefix=client_id_prefix,
        protocol=protocol,
        keep_alive=keep_alive,
        retain=retain,
        max_inflight_messages=max_inflight_messages,
        qos=qos,
        session_expiry=session_expiry,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def update_dataflow_endpoint_custom_mqtt(
    cmd,
    endpoint_name: str,
    instance_name: str,
    resource_group_name: str,
    hostname: Optional[str] = None,
    port: Optional[int] = None,
    keep_alive: Optional[int] = None,
    max_inflight_messages: Optional[int] = None,
    qos: Optional[int] = None,
    tls_disabled: Optional[bool] = None,
    no_auth: Optional[bool] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    sami_audience: Optional[str] = None,
    secret_name: Optional[str] = None,
    scope: Optional[str] = None,
    sat_audience: Optional[str] = None,
    client_id_prefix: Optional[str] = None,
    protocol: Optional[str] = None,
    retain: Optional[str] = None,
    session_expiry: Optional[int] = None,
    config_map_reference: Optional[str] = None,
    cloud_event_attribute: Optional[str] = None,
    authentication_type: Optional[str] = None,
    show_config: Optional[bool] = None,
) -> dict:

    return DataFlowEndpoints(cmd).update(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
        endpoint_type=DataflowEndpointType.CUSTOMMQTT.value,
        client_id=client_id,
        tenant_id=tenant_id,
        sami_audience=sami_audience,
        x509_secret_name=secret_name,
        scope=scope,
        sat_audience=sat_audience,
        hostname=hostname,
        port=port,
        client_id_prefix=client_id_prefix,
        protocol=protocol,
        keep_alive=keep_alive,
        retain=retain,
        max_inflight_messages=max_inflight_messages,
        qos=qos,
        session_expiry=session_expiry,
        tls_disabled=tls_disabled,
        config_map_reference=config_map_reference,
        cloud_event_attribute=cloud_event_attribute,
        no_auth=no_auth,
        authentication_type=authentication_type,
        show_config=show_config,
    )


def show_dataflow_endpoint(cmd, endpoint_name: str, instance_name: str, resource_group_name: str) -> dict:
    return DataFlowEndpoints(cmd).show(
        name=endpoint_name,
        instance_name=instance_name,
        resource_group_name=resource_group_name,
    )


def list_dataflow_endpoints(cmd, instance_name: str, resource_group_name: str) -> Iterable[dict]:
    return DataFlowEndpoints(cmd).list(instance_name=instance_name, resource_group_name=resource_group_name)
