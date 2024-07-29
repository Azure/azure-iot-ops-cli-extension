# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional

from .helper import get_resource_from_partial_id, ResourceKeys


def assert_broker_args(
    resource_group: str,
    init_resources: List[str],
    add_insecure_listener: Optional[bool] = None,
    broker: Optional[str] = None,
    broker_authn: Optional[str] = None,
    broker_listener: Optional[str] = None,
    broker_mem_profile: Optional[str] = None,
    broker_service_type: Optional[str] = None,
    broker_backend_part: Optional[str] = None,
    broker_backend_rf: Optional[str] = None,
    broker_backend_workers: Optional[str] = None,
    broker_frontend_replicas: Optional[str] = None,
    broker_frontend_workers: Optional[str] = None,
    bfr: Optional[str] = None,
    bfw: Optional[str] = None,
    **_
):
    if bfr:
        broker_frontend_replicas = bfr
    if bfw:
        broker_frontend_workers = bfw

    broker_resources = [res for res in init_resources if res.startswith(ResourceKeys.iot_operations.value)]
    instance_partial_id = broker_resources[0]
    broker_resources = set(broker_resources)

    # broker
    expected_broker_partial_id = f"{instance_partial_id}/brokers/{broker or 'broker'}"
    assert expected_broker_partial_id in broker_resources

    broker_obj = get_resource_from_partial_id(expected_broker_partial_id, resource_group)
    broker_props = broker_obj["properties"]
    assert broker_props["memoryProfile"].lower() == (broker_mem_profile or "medium")

    cardinality = broker_props["cardinality"]
    assert cardinality["backendChain"]["partitions"] == (broker_backend_part or 2)
    assert cardinality["backendChain"]["redundancyFactor"] == (broker_backend_rf or 2)
    assert cardinality["backendChain"]["workers"] == (broker_backend_workers or 2)
    assert cardinality["frontend"]["replicas"] == (broker_frontend_replicas or 2)
    assert cardinality["frontend"]["workers"] == (broker_frontend_workers or 2)
    # there is diagnostics + generateResourceLimits but nothing from init yet

    # nothing interesting in the authenticator
    expected_authn_partial_id = f"{expected_broker_partial_id}/authentications/{broker_authn or 'authn'}"
    assert expected_authn_partial_id in broker_resources
    get_resource_from_partial_id(expected_authn_partial_id, resource_group)

    # listener
    expected_listener_partial_id = f"{expected_broker_partial_id}/listeners/{broker_listener or 'listener'}"
    assert expected_listener_partial_id in broker_resources
    listener_obj = get_resource_from_partial_id(expected_listener_partial_id, resource_group)
    listener_props = listener_obj["properties"]
    assert listener_props["brokerRef"] == (broker or "broker")
    assert listener_props["serviceType"].lower() == (broker_service_type or "ClusterIp").lower()

    ports = listener_props["ports"]
    assert len(ports) == (2 if add_insecure_listener else 1)
    if add_insecure_listener:
        assert 1883 in [p['port'] for p in ports]
