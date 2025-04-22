# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from typing import TYPE_CHECKING, Iterable

from knack.log import get_logger
from rich.console import Console

from azure.cli.core.azclierror import InvalidArgumentValueError
from azext_edge.edge.providers.orchestration.common import AUTHENTICATION_TYPE_REQUIRED_PARAMS, DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP, DATAFLOW_ENDPOINT_TYPE_REQUIRED_PARAMS, DATAFLOW_ENDPOINT_TYPE_SETTINGS, DataflowEndpointModeType, DataflowEndpointType, DataflowEndpointAuthenticationType
from azext_edge.edge.providers.orchestration.resources.instances import Instances
from azext_edge.edge.providers.orchestration.resources.reskit import GetInstanceExtLoc, get_file_config
from azext_edge.edge.util.common import should_continue_prompt
from azext_edge.edge.util.file_operations import deserialize_file_content

from ....util.az_client import get_iotops_mgmt_client, wait_for_terminal_state
from ....util.queryable import Queryable

logger = get_logger(__name__)

console = Console()

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
        self.instances = Instances(cmd=cmd)
        self.dataflows = DataFlows(self.iotops_mgmt_client.dataflow, self.instances.get_ext_loc)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name, instance_name=instance_name, dataflow_profile_name=name
        )

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)


class DataFlows:
    def __init__(self, ops: "DataflowOperations", get_ext_loc: GetInstanceExtLoc):
        self.ops = ops
        self.get_ext_loc = get_ext_loc

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

        # format the endpoint host
        host = self._get_endpoint_host(
            endpoint_type=endpoint_type,
            **kwargs
        )

        self._process_authentication_type(
            endpoint_type=endpoint_type,
            settings=settings,
            **kwargs
        )

        self._process_endpoint_properties(
            endpoint_type=endpoint_type,
            settings=settings,
            host=host,
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
    
    def update(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        endpoint_type: DataflowEndpointType,
        **kwargs
    ) -> dict:
        self.instance = self.instances.show(name=instance_name, resource_group_name=resource_group_name)
        extended_location = self.instance["extendedLocation"]

        # get the original endpoint
        original_endpoint = self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=name,
        )
        # settings = {}

        self._update_properties(
            properties=original_endpoint["properties"],
            endpoint_type=endpoint_type,
            **kwargs
        )


        # self._process_authentication_type(
        #     endpoint_type=endpoint_type,
        #     settings=settings,
        #     **kwargs
        # )

        # self._process_endpoint_properties(
        #     endpoint_type=endpoint_type,
        #     settings=settings,
        #     host=host,
        #     **kwargs
        # )

        resource = {
            "extendedLocation": extended_location,
            "properties": original_endpoint["properties"],
        }

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=name,
                resource=resource,
            )
            return wait_for_terminal_state(poller)

    
    def import_endpoint(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        file_path: str,
        **kwargs
    ) -> dict:
        resource = {}
        endpoint_config = get_file_config(file_path)
        self.instance = self.instances.show(name=instance_name, resource_group_name=resource_group_name)
        resource["extendedLocation"] = self.instance["extendedLocation"]
        resource["properties"] = endpoint_config
        
        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                dataflow_endpoint_name=name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)
    

    def delete(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: bool = False,
        **kwargs
    ) -> dict:
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=name,
        )

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)


    def _get_endpoint_host(self, endpoint_type: DataflowEndpointType, **kwargs) -> str:
        host = ""
        if endpoint_type in [
            DataflowEndpointType.DATAEXPLORER.value,
            DataflowEndpointType.FABRICREALTIME.value,
        ]:
            host = kwargs["host"]
        elif endpoint_type == DataflowEndpointType.DATALAKESTORAGE.value:
            host = f"https://{kwargs['storage_account_name']}.blob.core.windows.net"
        elif endpoint_type == DataflowEndpointType.FABRICONELAKE.value:
            host = "https://onelake.dfs.fabric.microsoft.com"
        elif endpoint_type == DataflowEndpointType.EVENTHUB.value:
            host = f"{kwargs['eventhub_namespace']}.servicebus.windows.net:9093"
        elif endpoint_type in [
            DataflowEndpointType.CUSTOMKAFKA.value,
            DataflowEndpointType.AIOLOCALMQTT.value,
            DataflowEndpointType.EVENTGRID.value,
            DataflowEndpointType.CUSTOMMQTT.value,
        ]:
            host = f"{kwargs["host"]}:{kwargs["port"]}"
        
        return host

    def _process_authentication_type(
        self,
        endpoint_type: DataflowEndpointType,
        settings: dict,
        **kwargs
    ):
        # No authentication method required for local storage
        if endpoint_type == DataflowEndpointType.LOCALSTORAGE.value:
            return
        
        # Identify authentication method using the provided kwargs
        authentication_method = self._identify_authentication_method(
            **kwargs
        )
        
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
    

    def _identify_authentication_method(
        self,
        **kwargs
    ) -> str:
        # Check for the presence of authentication-related parameters in kwargs
        if kwargs.get("no_auth"):
            return DataflowEndpointAuthenticationType.ANONYMOUS.value
        elif kwargs.get("client_id") and kwargs.get("tenant_id"):
            return DataflowEndpointAuthenticationType.USERASSIGNED.value
        elif kwargs.get("sat_audience"):
            return DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value
        elif kwargs.get("x509_secret_name"):
            return DataflowEndpointAuthenticationType.X509.value
        elif kwargs.get("sasl_type"):
            return DataflowEndpointAuthenticationType.SASL.value
        elif kwargs.get("at_secret_name"):
            return DataflowEndpointAuthenticationType.ACCESSTOKEN.value
        else:
            return DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value
    

    def _process_endpoint_properties(
        self,
        settings: dict,
        host: str,
        **kwargs
    ):
        if host:
            settings["host"] = host
        if kwargs.get("database_name"):
            settings["database"] = kwargs["database_name"]
        if kwargs.get("latency") or kwargs.get("message_count") or kwargs.get("batching_disabled") or kwargs.get("max_byte") or kwargs.get("latency_ms"):
            settings["batching"] = {}
            if kwargs.get("latency"):
                settings["batching"]["latencySeconds"] = kwargs["latency"]
            if kwargs.get("latency_ms"):
                settings["batching"]["latencyMs"] = kwargs["latency_ms"]
            if kwargs.get("message_count"):
                settings["batching"]["maxMessages"] = kwargs["message_count"]
            if kwargs.get("batching_disabled"):
                settings["batching"]["mode"] = DataflowEndpointModeType.DISABLED.value if kwargs["batching_disabled"] else DataflowEndpointModeType.ENABLED.value
            if kwargs.get("max_byte"):
                settings["batching"]["maxBytes"] = kwargs["max_byte"]
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
            settings["copyMqttProperties"] = DataflowEndpointModeType.DISABLED.value if kwargs["copy_broker_props_disabled"] else DataflowEndpointModeType.ENABLED.value
        if kwargs.get("compression"):
            settings["compression"] = kwargs["compression"]
        if kwargs.get("aks"):
            settings["aks"] = kwargs["aks"]
        if kwargs.get("patition_strategy"):
            settings["partitionStrategy"] = kwargs["patition_strategy"]
        if kwargs.get("tls_disabled") or kwargs.get("tls_config_map_reference"):
            settings["tls"] = {}
            if kwargs.get("tls_disabled"):
                settings["tls"]["mode"] = DataflowEndpointModeType.DISABLED.value if kwargs["tls_disabled"] else DataflowEndpointModeType.ENABLED.value
            if kwargs.get("tls_config_map_reference"):
                settings["tls"]["trustedCaCertificateConfigMapRef"] = kwargs["tls_config_map_reference"]
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
    
    def _update_properties(
        self,
        properties: dict,
        endpoint_type: DataflowEndpointType,
        **kwargs
    ):
        if any(
            kwargs["host"],
            kwargs['storage_account_name'],
            kwargs['eventhub_namespace'],
            kwargs["port"]
        ):
            host = self._get_endpoint_host(
                endpoint_type=endpoint_type,
                **kwargs
            )

            if host and host is not properties["host"]:
                properties["host"] = host

        if any(
            kwargs["client_id"],
            kwargs["tenant_id"],
            kwargs["sat_audience"],
            kwargs["x509_secret_name"],
            kwargs["sasl_type"],
            kwargs["at_secret_name"],
            kwargs["no_auth"],
        ):
            self._process_authentication_type(
                endpoint_type=endpoint_type,
                settings=properties,
                **kwargs
            )
        
        self._process_endpoint_properties(
            settings=properties,
            host=properties["host"],
            **kwargs
        )