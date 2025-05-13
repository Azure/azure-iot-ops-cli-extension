# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger
from rich.console import Console

from azure.cli.core.azclierror import InvalidArgumentValueError
from azext_edge.edge.providers.orchestration.common import AUTHENTICATION_TYPE_REQUIRED_PARAMS, DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP, DATAFLOW_ENDPOINT_TYPE_SETTINGS, DataflowEndpointModeType, DataflowEndpointType, DataflowEndpointAuthenticationType
from azext_edge.edge.providers.orchestration.resources.instances import Instances
from azext_edge.edge.providers.orchestration.resources.reskit import GetInstanceExtLoc, get_file_config
from azext_edge.edge.util.common import should_continue_prompt
from azext_edge.edge.util.file_operations import deserialize_file_content

from ....util.az_client import get_iotops_mgmt_client, wait_for_terminal_state
from azure.core.exceptions import ResourceNotFoundError
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge.providers.orchestration.common import (
    DATAFLOW_ENDPOINT_TYPE_SETTINGS,
    DATAFLOW_OPERATION_TYPE_SETTINGS,
    DataflowEndpointType,
    DataflowOperationType,
)

from ....util.common import should_continue_prompt
from ....util.az_client import wait_for_terminal_state
from ....util.queryable import Queryable
from .instances import Instances
from .reskit import GetInstanceExtLoc, get_file_config

logger = get_logger(__name__)

console = Console()

LOCAL_MQTT_HOST_PREFIX = "aio-broker"


if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        DataflowEndpointOperations,
        DataflowOperations,
        DataflowProfileOperations,
    )

console = Console()


class DataFlowProfiles(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(cmd=cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client
        self.ops: "DataflowProfileOperations" = self.iotops_mgmt_client.dataflow_profile
        self.dataflows = DataFlows(
            ops_dataflow=self.iotops_mgmt_client.dataflow,
            ops_endpoint=self.iotops_mgmt_client.dataflow_endpoint,
            get_ext_loc=self.instances.get_ext_loc,
        )

    def create(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        profile_instances: int = 1,
        log_level: str = "info",
        **kwargs,
    ):

        resource = {
            "properties": {
                "diagnostics": {
                    "logs": {"level": log_level},
                },
                "instanceCount": profile_instances,
            },
            "extendedLocation": self.instances.get_ext_loc(
                name=instance_name, resource_group_name=resource_group_name
            ),
        }

        with console.status(f"Creating {name}..."):
            poller = self.ops.begin_create_or_update(
                instance_name=instance_name,
                dataflow_profile_name=name,
                resource_group_name=resource_group_name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def update(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        profile_instances: Optional[int] = None,
        log_level: Optional[str] = None,
        **kwargs,
    ):
        # get the existing dataflow profile
        original_profile = self.show(
            name=name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

        # update the properties
        if profile_instances:
            properties = original_profile.setdefault("properties", {})
            properties["instanceCount"] = profile_instances
        if log_level:
            properties = original_profile.setdefault("properties", {})
            diagnostics = properties.setdefault("diagnostics", {})
            logs = diagnostics.setdefault("logs", {})
            logs["level"] = log_level

        with console.status(f"Updating {name}..."):
            poller = self.ops.begin_create_or_update(
                instance_name=instance_name,
                dataflow_profile_name=name,
                resource_group_name=resource_group_name,
                resource=original_profile,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ):
        dataflows = self.dataflows.list(
            dataflow_profile_name=name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
        dataflows = list(dataflows)

        if name == "default":
            logger.warning("Deleting the 'default' dataflow profile may cause disruptions.")

        if dataflows:
            console.print("Deleting this dataflow profile will also affect the associated dataflows:")
            for dataflow in dataflows:
                console.print(f"\t- {dataflow['name']}")

        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status(f"Deleting {name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_profile_name=name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=name,
        )

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)


class DataFlows:
    def __init__(
        self,
        ops_dataflow: "DataflowOperations",
        ops_endpoint: "DataflowEndpointOperations",
        get_ext_loc: GetInstanceExtLoc
    ):
        self.ops_dataflow = ops_dataflow
        self.ops_endpoint = ops_endpoint
        self.get_ext_loc = get_ext_loc

    def show(
        self,
        name: str,
        dataflow_profile_name: str,
        instance_name: str,
        resource_group_name: str,
    ) -> dict:
        return self.ops_dataflow.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
            dataflow_name=name,
        )

    def list(self, dataflow_profile_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops_dataflow.list_by_profile_resource(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_profile_name=dataflow_profile_name,
        )

    def apply(
        self,
        name: str,
        dataflow_profile_name: str,
        instance_name: str,
        resource_group_name: str,
        config_file: str,
        **kwargs
    ) -> dict:
        resource = {}
        dataflow_config = get_file_config(config_file)
        resource["extendedLocation"] = self.get_ext_loc(
            name=instance_name,
            resource_group_name=resource_group_name,
        )
        resource["properties"] = dataflow_config

        # Validation for the config file
        self._validate_dataflow_config(
            dataflow_config=dataflow_config,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

        with console.status("Working..."):
            poller = self.ops_dataflow.begin_create_or_update(
                dataflow_profile_name=dataflow_profile_name,
                dataflow_name=name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        name: str,
        dataflow_profile_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs
    ) -> dict:
        should_bail = not should_continue_prompt(
            confirm_yes=confirm_yes,
        )
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops_dataflow.begin_delete(
                dataflow_profile_name=dataflow_profile_name,
                dataflow_name=name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def _validate_dataflow_config(
        self,
        dataflow_config: dict,
        instance_name: str,
        resource_group_name: str,
    ):
        operations = dataflow_config.get("operations", [])

        # get source endpoint
        source_endpoint_obj = self._process_existing_endpoint(
            operations=operations,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            operation_type=DataflowOperationType.SOURCE.value,
        )

        # validate source endpoint type
        source_endpoint_type = source_endpoint_obj.get("properties", {}).get("endpointType", "")
        if source_endpoint_type not in [
            DataflowEndpointType.KAFKA.value,
            DataflowEndpointType.MQTT.value,
        ]:
            raise InvalidArgumentValueError(
                f"'{source_endpoint_type}' is not a valid type for source dataflow endpoint."
            )

        # if Kafka endpoint, validate consumer group id
        if source_endpoint_type == DataflowEndpointType.KAFKA.value:
            group_id = source_endpoint_obj.get("properties", {}).get("kafkaSettings", {}).get("consumerGroupId", "")
            if not group_id:
                raise InvalidArgumentValueError(
                    "'consumerGroupId' is required in kafka source dataflow endpoint configuration."
                )

        # get destination endpoint
        desination_endpoint_obj = self._process_existing_endpoint(
            operations=operations,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            operation_type=DataflowOperationType.DESTINATION.value,
        )

        trans_operation_type = DataflowOperationType.TRANSFORMATION.value
        transformation_operation = self._get_operation(
            operations=operations,
            operation_type=trans_operation_type,
        )
        schema_ref = transformation_operation.get(
            DATAFLOW_OPERATION_TYPE_SETTINGS[trans_operation_type], {}).get("schemaRef", "")

        # validate schema_ref for destination endpoint type
        destination_endpoint_type = desination_endpoint_obj.get("properties", {}).get("endpointType", "")
        if destination_endpoint_type in [
            DataflowEndpointType.DATAEXPLORER.value,
            DataflowEndpointType.DATALAKESTORAGE.value,
            DataflowEndpointType.FABRICONELAKE.value,
            DataflowEndpointType.LOCALSTORAGE.value,
        ] and not schema_ref:
            raise InvalidArgumentValueError(
                f"'schemaRef' is required for destination endpoint '{destination_endpoint_type}' type."
            )

        # validate at least one of source and destination endpoint
        # must have host with "aio-broker" that is MQTT endpoint
        source_endpoint_host = source_endpoint_obj.get("properties", {}).get(
            DATAFLOW_ENDPOINT_TYPE_SETTINGS[source_endpoint_type], {}).get("host", "")
        destination_endpoint_host = desination_endpoint_obj.get("properties", {}).get(
            DATAFLOW_ENDPOINT_TYPE_SETTINGS[destination_endpoint_type], {}).get("host", "")
        is_source_local_mqtt = LOCAL_MQTT_HOST_PREFIX in source_endpoint_host and\
            source_endpoint_type == DataflowEndpointType.MQTT.value
        is_destination_local_mqtt = LOCAL_MQTT_HOST_PREFIX in destination_endpoint_host and\
            destination_endpoint_type == DataflowEndpointType.MQTT.value
        if not is_source_local_mqtt and not is_destination_local_mqtt:
            raise InvalidArgumentValueError(
                "Either source or destination endpoint must be an Azure IoT Operations Local "
                f"MQTT endpoint with the 'host' containing '{LOCAL_MQTT_HOST_PREFIX}'."
            )

    def _process_existing_endpoint(
        self,
        operations: list,
        instance_name: str,
        resource_group_name: str,
        operation_type: str,
    ) -> dict:
        # get endpoint
        operation = self._get_operation(
            operations=operations,
            operation_type=operation_type,
        )

        # get operation settings
        operation_settings = operation.get(DATAFLOW_OPERATION_TYPE_SETTINGS[operation_type], {})
        endpoint_name = operation_settings.get("endpointRef", "")

        # call get_dataflow_endpoint
        endpoint_obj = self.ops_endpoint.get(
            instance_name=instance_name,
            resource_group_name=resource_group_name,
            dataflow_endpoint_name=endpoint_name,
        )

        if not endpoint_obj:
            raise ResourceNotFoundError(
                f"{operation_type} dataflow endpoint '{endpoint_name}' not found in instance '{instance_name}'. "
                "Please provide a valid 'endpointRef' using --config-file."
            )

        return endpoint_obj

    def _get_operation(
        self,
        operations: list,
        operation_type: str,
    ) -> dict:
        operation = next(
            (op for op in operations if op.get("operationType") == operation_type), {}
        )
        return operation


class DataFlowEndpoints(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(self.cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client
        self.ops: "DataflowEndpointOperations" = self.iotops_mgmt_client.dataflow_endpoint
        self.instances = Instances(self.cmd)
    
    def create(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        endpoint_type: DataflowEndpointType,
        show_config: Optional[bool] = None,
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

        actual_endpoint_type = endpoint_type
        
        if endpoint_type in [
            DataflowEndpointType.FABRICREALTIME.value,
            DataflowEndpointType.EVENTHUB.value,
            DataflowEndpointType.CUSTOMKAFKA.value,
        ]:
            actual_endpoint_type = "Kafka"
        elif endpoint_type in [
            DataflowEndpointType.AIOLOCALMQTT.value,
            DataflowEndpointType.EVENTGRID.value,
            DataflowEndpointType.CUSTOMMQTT.value,
        ]:
            actual_endpoint_type = "Mqtt"

        resource = {
            "extendedLocation": extended_location,
            "properties": {
                "endpointType": actual_endpoint_type,
                DATAFLOW_ENDPOINT_TYPE_SETTINGS[endpoint_type]: settings,
            }
        }

        if show_config:
            return resource["properties"]

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)
    
    def update(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        endpoint_type: DataflowEndpointType,
        show_config: Optional[bool] = None,
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

        if show_config:
            return resource["properties"]

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                dataflow_endpoint_name=name,
                resource=resource,
            )
            return wait_for_terminal_state(poller)

    
    def apply(
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

    def apply(
        self,
        name: str,
        instance_name: str,
        resource_group_name: str,
        config_file: str,
        **kwargs
    ) -> dict:
        resource = {}
        endpoint_config = get_file_config(config_file)
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
    ):
        should_bail = not should_continue_prompt(
            confirm_yes=confirm_yes,
        )
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
        
        if kwargs.get("authentication_type"):
            authentication_method = kwargs["authentication_type"]
        else:
            # Identify authentication method using the provided kwargs
            authentication_method = self._identify_authentication_method(
                **kwargs
            )
        
        # Check if authentication method is allowed for the given endpoint type
        if authentication_method not in DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP[endpoint_type]:
            raise ValueError(
                f"Authentication method '{authentication_method}' is not allowed for endpoint type '{endpoint_type}'. "
                f"Allowed methods are: {DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP[endpoint_type]}"
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

        # lower the first letter of the authentication method
        auth_setting_name = authentication_method[0].lower() + authentication_method[1:] + "Settings"
        settings["authentication"][auth_setting_name] = auth_settings
        
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
        endpoint_type: DataflowEndpointType,
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
        
        # for eventhub and eventgrid, tls mode is always enabled
        if endpoint_type in [
            DataflowEndpointType.EVENTHUB.value,
            DataflowEndpointType.EVENTGRID.value,
        ]:
            import pdb; pdb.set_trace()
            if settings.get("tls"):
                settings["tls"]["mode"] = DataflowEndpointModeType.ENABLED.value
            else:
                settings["tls"] = {"mode": DataflowEndpointModeType.ENABLED.value}

        return
    
    def _update_properties(
        self,
        properties: dict,
        endpoint_type: DataflowEndpointType,
        **kwargs
    ):
        settings = properties.get(DATAFLOW_ENDPOINT_TYPE_SETTINGS[endpoint_type], {})
        if any([
            kwargs.get("host"),
            kwargs.get('storage_account_name'),
            kwargs.get('eventhub_namespace'),
            kwargs.get("port")
        ]):
            host = self._get_endpoint_host(
                endpoint_type=endpoint_type,
                **kwargs
            )

            if host and host is not settings["host"]:
                settings["host"] = host

        if any([
            kwargs.get("client_id"),
            kwargs.get("tenant_id"),
            kwargs.get("sat_audience"),
            kwargs.get("x509_secret_name"),
            kwargs.get("sasl_type"),
            kwargs.get("at_secret_name"),
            kwargs.get("no_auth"),
        ]):
            self._process_authentication_type(
                endpoint_type=endpoint_type,
                settings=settings,
                **kwargs
            )
        
        self._process_endpoint_properties(
            endpoint_type=endpoint_type,
            settings=settings,
            host=settings.get("host"),
            **kwargs
        )