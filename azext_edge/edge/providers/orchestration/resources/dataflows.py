# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable

from knack.log import get_logger

from azext_edge.edge.providers.orchestration.common import AUTHENTICATION_TYPE_REQUIRED_PARAMS, DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP, DATAFLOW_ENDPOINT_TYPE_REQUIRED_PARAMS, DATAFLOW_ENDPOINT_TYPE_SETTINGS, DataflowEndpointType, DataflowEndpointAuthenticationType
from azext_edge.edge.providers.orchestration.resources.instances import Instances

from ....util.az_client import get_iotops_mgmt_client
from ....util.queryable import Queryable

logger = get_logger(__name__)


if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        DataflowEndpointOperations,
        DataflowOperations,
        DataflowProfileOperations,
    )


class DataFlowProfiles(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "DataflowProfileOperations" = self.iotops_mgmt_client.dataflow_profile
        self.dataflows = DataFlows(self.iotops_mgmt_client.dataflow)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name, instance_name=instance_name, dataflow_profile_name=name
        )

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)


class DataFlows:
    def __init__(self, ops: "DataflowOperations"):
        self.ops = ops

    def show(self, name: str, dataflow_profile_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
            dataflow_name=name,
        )

    def list(self, dataflow_profile_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_profile_resource(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
        )


class DataFlowEndpoints(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.iotops_mgmt_client = get_iotops_mgmt_client(
            subscription_id=self.default_subscription_id,
        )
        self.ops: "DataflowEndpointOperations" = self.iotops_mgmt_client.dataflow_endpoint
        self.instances = Instances(self.cmd)
    
    def create(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        endpoint_type: DataflowEndpointType,
        **kwargs
    ) -> dict:
        self.instance = self.instances.show(name=instance_name, resource_group_name=resource_group_name)
        extended_location = self.instance["extendedLocation"]
        settings = {}

        self._process_authentication_type(
            endpoint_type=endpoint_type,
            authentication_method=kwargs.get("authentication_method"),
            settings=settings,
            **kwargs
        )

        self._process_endpoint_properties(
            endpoint_type=endpoint_type,
            settings=settings,
            **kwargs
        )

        resource = {
            "extendedLocation": extended_location,
            "properties": {
                "endpointType": endpoint_type.value,
                DATAFLOW_ENDPOINT_TYPE_SETTINGS[endpoint_type.value]: settings,
            }
        }

        return self.ops.begin_create_or_update(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=name,
            resource=resource,
        )

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=name,
        )

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)


    def _process_authentication_type(
        self,
        endpoint_type: DataflowEndpointType,
        authentication_method: DataflowEndpointAuthenticationType,
        settings: dict,
        **kwargs
    ):
        # No authentication method required for local storage
        if endpoint_type == DataflowEndpointType.LOCALSTORAGE.value:
            return
        
        # Check if authentication method is allowed for the given endpoint type
        if authentication_method not in DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP[endpoint_type.value]:
            raise ValueError(
                f"Authentication method '{authentication_method}' is not allowed for endpoint type '{endpoint_type}'. "
                f"Allowed methods are: {DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP[endpoint_type.value]}"
            )
        
        # Check required properties for authentication method
        required_params = AUTHENTICATION_TYPE_REQUIRED_PARAMS.get(authentication_method, [])
        missing_params = [param for param in required_params if param not in kwargs]

        if missing_params:
            raise ValueError(
                f"Missing required parameters for authentication method '{authentication_method}': {', '.join(missing_params)}"
            )
        
        settings["authentication"] = {
            "method": authentication_method,
        }

        if authentication_method == DataflowEndpointAuthenticationType.ANONYMOUS.value:
            return

        auth_settings = {}
        for param_name, property_name in [
            ("audience", "audience"),
            ("client_id", "clientId"),
            ("tenant_id", "tenantId"),
            ("scope", "scope"),
            ("secret_name", "secretRef"),
            ("sasl_type", "saslType"),
        ]:
            if kwargs.get(param_name):
                auth_settings[property_name] = kwargs[param_name]

        settings["authentication"][DataflowEndpointAuthenticationType.ANONYMOUS.value+"Settings"] = auth_settings
        
        return
    

    def _process_endpoint_properties(
        self,
        endpoint_type: DataflowEndpointType,
        settings: dict,
        **kwargs
    ):
        # # Check required properties for endpoint type
        # required_params = DATAFLOW_ENDPOINT_TYPE_REQUIRED_PARAMS.get(endpoint_type.value, [])
        # missing_params = [param for param in required_params if param not in kwargs]

        # if missing_params:
        #     raise ValueError(
        #         f"Missing required parameters for endpoint type '{endpoint_type}': {', '.join(missing_params)}"
        #     )
        
        if kwargs.get("database_name"):
            settings["database"] = kwargs["database_name"]
        if kwargs.get("host"):
            settings["host"] = kwargs["host"]
        if kwargs.get("batching_latency") or kwargs.get("message_count"):
            settings["batching"] = {}
            if kwargs.get("batching_latency"):
                settings["batching"]["latencySeconds"] = kwargs["batching_latency"]
            if kwargs.get("message_count"):
                settings["batching"]["maxMessages"] = kwargs["message_count"]
        if kwargs.get("lakehouse_name") or kwargs.get("workspace_name"):
            settings["names"] = {}
            if kwargs.get("lakehouse_name"):
                settings["names"]["lakehouseName"] = kwargs["lakehouse_name"]
            if kwargs.get("workspace_name"):
                settings["names"]["workspaceName"] = kwargs["workspace_name"]
        if kwargs.get("path_type"):
            settings["oneLakePathType"] = kwargs["path_type"]
        if kwargs.get("group_id"):
            settings["consumerGroupId"] = kwargs["group_id"]
        if kwargs.get("copy_broker_props_disabled"):
            settings["copyMqttProperties"] = not kwargs["copy_broker_props_disabled"]
        if kwargs.get("compression"):
            settings["compression"] = kwargs["compression"]
        if kwargs.get("aks"):
            settings["aks"] = kwargs["aks"]
        if kwargs.get("patition_strategy"):
            settings["partitionStrategy"] = kwargs["patition_strategy"]
        if kwargs.get("tls_disabled") or kwargs.get("tls_config_map_reference"):
            settings["tls"] = {}
            if kwargs.get("tls_disabled"):
                settings["tls"]["mode"] = not kwargs["tls_disabled"]
            if kwargs.get("tls_config_map_reference"):
                settings["tls"]["configMapRef"] = kwargs["tls_config_map_reference"]
        if kwargs.get("cloud_event_attribute"):
            settings["cloudEventAttributes"] = kwargs["cloud_event_attribute"]
        if kwargs.get("pvc_reference"):
            settings["persistentVolumeClaimRef"] = kwargs["pvc_reference"]
        if kwargs.get("client_id_prefix"):
            settings["clientIdPrefix"] = kwargs["client_id_prefix"]
        if kwargs.get("protocol"):
            settings["protocol"] = kwargs["protocol"]
        if kwargs.get("keep_alive"):
            settings["keepAliveSeconds"] = kwargs["keep_alive"]
        if kwargs.get("retain"):
            settings["retain"] = kwargs["retain"]
        if kwargs.get("max_inflight_messages"):
            settings["maxInflightMessages"] = kwargs["max_inflight_messages"]
        if kwargs.get("qos"):
            settings["qos"] = kwargs["qos"]
        if kwargs.get("session_expiry"):
            settings["sessionExpirySeconds"] = kwargs["session_expiry"]
        
        return
