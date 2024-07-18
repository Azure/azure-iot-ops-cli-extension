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
    add_insecure_listener: Optional[str] = None,
    broker: Optional[str] = None,
    broker_authn: Optional[str] = None,
    broker_frontend_server: Optional[str] = None,
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
    assert broker_obj["properties"]["memoryProfile"] == (broker_mem_profile or "medium")
    assert broker_obj["properties"]["encryptInternalTraffic"] is not add_insecure_listener

    cardinality = broker_obj["properties"]["cardinality"]
    assert cardinality["backendChain"]["partitions"] == (broker_backend_part or 2)
    assert cardinality["backendChain"]["redundancyFactor"] == (broker_backend_rf or 2)
    assert cardinality["backendChain"]["workers"] == (broker_backend_workers or 2)
    assert cardinality["frontend"]["replicas"] == (broker_frontend_replicas or 2)
    assert cardinality["frontend"]["workers"] == (broker_frontend_workers or 2)

    # nothing interesting in the authenticator
    expected_authn_partial_id = f"{expected_broker_partial_id}/authentication/{broker_authn or 'authn'}"
    assert expected_authn_partial_id in broker_resources
    get_resource_from_partial_id(expected_authn_partial_id, resource_group)

    # listener
    expected_listener_partial_id = f"{expected_broker_partial_id}/listeners/{broker_listener or 'listener'}"
    assert expected_listener_partial_id in broker_resources
    listener_obj = get_resource_from_partial_id(expected_listener_partial_id, resource_group)
    assert listener_obj["properties"]["serviceType"] == (broker_service_type or "clusterIp")
    assert listener_obj["properties"]["tls"]["automatic"]["issuerRef"]["name"] == (
        broker_frontend_server or "mq-dmqtt-frontend"
    )

    # if add_insecure_listener:
    #     assert broker_resources[4].split("/")[-1] == "non-tls-listener"
    #     get_resource_from_partial_id(broker_resources[4], resource_group)

    # # nothing interesting in the diagnostics
    # assert broker_resources[-1].split("/")[-1] == "diagnostics"
    # get_resource_from_partial_id(broker_resources[4], resource_group)
