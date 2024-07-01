# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional

from .helper import get_resource_from_partial_id, ResourceKeys


def assert_mq_args(
    resource_group: str,
    init_resources: List[str],
    mq_authn: Optional[str] = None,
    mq_broker: Optional[str] = None,
    mq_frontend_server: Optional[str] = None,
    mq_insecure: Optional[bool] = None,
    mq_instance: Optional[str] = None,
    mq_listener: Optional[str] = None,
    mq_mem_profile: Optional[str] = None,
    mq_mode: Optional[str] = None,
    mq_service_type: Optional[str] = None,
    mq_backend_part: Optional[str] = None,
    mq_backend_rf: Optional[str] = None,
    mq_backend_workers: Optional[str] = None,
    mq_frontend_replicas: Optional[str] = None,
    mq_frontend_workers: Optional[str] = None,
    **_
):
    mq_resources = [res for res in init_resources if res.startswith(ResourceKeys.mq.value)]
    mq_name = mq_resources[0].split("/")[-1]
    if mq_instance:
        assert mq_instance == mq_name
    else:
        assert mq_name.startswith("init-")
        assert mq_name.endswith("-mq-instance")

    # there isn't anything interesting in the resource
    get_resource_from_partial_id(mq_resources[0], resource_group)

    # broker
    assert mq_resources[1].split("/")[-1] == (mq_broker or "broker")
    broker_obj = get_resource_from_partial_id(mq_resources[1], resource_group)
    assert broker_obj["properties"]["memoryProfile"] == (mq_mem_profile or "medium")
    assert broker_obj["properties"]["mode"] == (mq_mode or "distributed")
    assert broker_obj["properties"]["encryptInternalTraffic"] is not mq_insecure

    cardinality = broker_obj["properties"]["cardinality"]
    assert cardinality["backendChain"]["partitions"] == (mq_backend_part or 2)
    assert cardinality["backendChain"]["redundancyFactor"] == (mq_backend_rf or 2)
    assert cardinality["backendChain"]["workers"] == (mq_backend_workers or 2)
    assert cardinality["frontend"]["replicas"] == (mq_frontend_replicas or 2)
    assert cardinality["frontend"]["workers"] == (mq_frontend_workers or 2)

    # nothing interesting in the authenticator
    assert mq_resources[2].split("/")[-1] == (mq_authn or "authn")
    get_resource_from_partial_id(mq_resources[2], resource_group)

    # listener
    assert mq_resources[3].split("/")[-1] == (mq_listener or "listener")
    listener_obj = get_resource_from_partial_id(mq_resources[3], resource_group)
    assert listener_obj["properties"]["serviceType"] == (mq_service_type or "clusterIp")
    assert listener_obj["properties"]["tls"]["automatic"]["issuerRef"]["name"] == (mq_frontend_server or "mq-dmqtt-frontend")

    if mq_insecure:
        assert mq_resources[4].split("/")[-1] == "non-tls-listener"
        get_resource_from_partial_id(mq_resources[4], resource_group)

    # nothing interesting in the diagnostics
    assert mq_resources[-1].split("/")[-1] == "diagnostics"
    get_resource_from_partial_id(mq_resources[4], resource_group)
