# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger
from rich.console import Console

from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.core.exceptions import ResourceNotFoundError

from ....util.common import should_continue_prompt
from ....util.az_client import wait_for_terminal_state
from ....util.queryable import Queryable
from ..common import (
    AUTHENTICATION_TYPE_REQUIRED_PARAMS,
    AUTHENTICATION_TYPE_PARAMS_TEXT_MAP,
    DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP,
    DATAFLOW_ENDPOINT_TYPE_SETTINGS,
    DATAFLOW_OPERATION_TYPE_SETTINGS,
    KAFKA_ENDPOINT_TYPE,
    MQTT_ENDPOINT_TYPE,
    DataflowEndpointType,
    DataflowOperationType,
    DataflowEndpointModeType,
    DataflowEndpointAuthenticationType,
)
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
            KAFKA_ENDPOINT_TYPE,
            MQTT_ENDPOINT_TYPE,
        ]:
            raise InvalidArgumentValueError(
                f"'{source_endpoint_type}' is not a valid type for source dataflow endpoint."
            )

        # if Kafka endpoint, validate consumer group id
        if source_endpoint_type == KAFKA_ENDPOINT_TYPE:
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
            source_endpoint_type == MQTT_ENDPOINT_TYPE
        is_destination_local_mqtt = LOCAL_MQTT_HOST_PREFIX in destination_endpoint_host and\
            destination_endpoint_type == MQTT_ENDPOINT_TYPE
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
        extended_location = self.instances.get_ext_loc(
            name=instance_name,
            resource_group_name=resource_group_name,
        )
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

        if host and kwargs.get("host"):
            del kwargs["host"]
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
            actual_endpoint_type = KAFKA_ENDPOINT_TYPE
        elif endpoint_type in [
            DataflowEndpointType.AIOLOCALMQTT.value,
            DataflowEndpointType.EVENTGRID.value,
            DataflowEndpointType.CUSTOMMQTT.value,
        ]:
            actual_endpoint_type = MQTT_ENDPOINT_TYPE

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
        extended_location = self.instances.get_ext_loc(
            name=instance_name,
            resource_group_name=resource_group_name,
        )

        # get the original endpoint
        original_endpoint = self.ops.get(
            resource_group_name=resource_group_name,
            instance_name=instance_name,
            dataflow_endpoint_name=name,
        )

        self._update_properties(
            properties=original_endpoint["properties"],
            endpoint_type=endpoint_type,
            **kwargs
        )

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
        config_file: str,
        **kwargs
    ) -> dict:
        resource = {}
        endpoint_config = get_file_config(config_file)
        resource["extendedLocation"] = self.instances.get_ext_loc(
            name=instance_name,
            resource_group_name=resource_group_name,
        )
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

    def _get_endpoint_host(
        self,
        endpoint_type: DataflowEndpointType,
        host: Optional[str] = None,
        storage_account_name: Optional[str] = None,
        eventhub_namespace: Optional[str] = None,
        hostname: Optional[str] = None,
        port: Optional[str] = None,
        **_
    ) -> str:
        processed_host = ""
        if endpoint_type in [
            DataflowEndpointType.DATAEXPLORER.value,
            DataflowEndpointType.FABRICREALTIME.value,
        ]:
            processed_host = host
        elif endpoint_type == DataflowEndpointType.DATALAKESTORAGE.value:
            processed_host = f"https://{storage_account_name}.blob.core.windows.net"
        elif endpoint_type == DataflowEndpointType.FABRICONELAKE.value:
            processed_host = "https://onelake.dfs.fabric.microsoft.com"
        elif endpoint_type == DataflowEndpointType.EVENTHUB.value:
            processed_host = f"{eventhub_namespace}.servicebus.windows.net:9093"
        elif endpoint_type in [
            DataflowEndpointType.CUSTOMKAFKA.value,
            DataflowEndpointType.AIOLOCALMQTT.value,
            DataflowEndpointType.EVENTGRID.value,
            DataflowEndpointType.CUSTOMMQTT.value,
        ]:
            processed_host = f"{hostname}:{port}"

        return processed_host

    def _process_authentication_type(
        self,
        endpoint_type: DataflowEndpointType,
        settings: dict,
        authentication_type: Optional[str] = None,
        **kwargs
    ):
        # No authentication method required for local storage
        if endpoint_type == DataflowEndpointType.LOCALSTORAGE.value:
            return

        if authentication_type:
            authentication_method = authentication_type
        else:
            # Identify authentication method using the provided kwargs
            authentication_method = self._identify_authentication_method(
                **kwargs
            )

        should_check_missing_params = False
        original_auth_method = settings.get("authentication", {}).get("method")
        if not original_auth_method:
            should_check_missing_params = True
        elif original_auth_method and original_auth_method != authentication_method:
            should_check_missing_params = True
            settings["authentication"] = {
                "method": authentication_method,
            }

        # Check if authentication method is allowed for the given endpoint type
        if authentication_method not in DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP[endpoint_type]:
            supported_auths = list(sorted(DATAFLOW_ENDPOINT_AUTHENTICATION_TYPE_MAP[endpoint_type]))
            if DataflowEndpointAuthenticationType.ANONYMOUS.value in supported_auths:
                supported_auths.remove(DataflowEndpointAuthenticationType.ANONYMOUS.value)
            raise InvalidArgumentValueError(
                f"Authentication method '{authentication_method}' is not allowed for endpoint type '{endpoint_type}'. "
                f"Allowed methods are: {supported_auths}."
            )

        if should_check_missing_params:
            # Check required properties for authentication method
            required_params = AUTHENTICATION_TYPE_REQUIRED_PARAMS.get(authentication_method, [])
            missing_params = sorted([param for param in required_params if param not in kwargs or not kwargs[param]])

            if missing_params:
                missing_params_texts = [
                    AUTHENTICATION_TYPE_PARAMS_TEXT_MAP[param] for param in missing_params
                ]
                raise InvalidArgumentValueError(
                    "Missing required parameters for authentication method "
                    f"'{authentication_method}': {', '.join(missing_params_texts)}."
                )

        settings["authentication"] = settings.get("authentication", {
            "method": authentication_method,
        })

        if authentication_method == DataflowEndpointAuthenticationType.ANONYMOUS.value:
            return

        auth_settings = {}
        for param_name, property_name in [
            ("sat_audience", "audience"),
            ("sami_audience", "audience"),
            ("audience", "audience"),
            ("client_id", "clientId"),
            ("tenant_id", "tenantId"),
            ("scope", "scope"),
            ("at_secret_name", "secretRef"),
            ("sasl_secret_name", "secretRef"),
            ("x509_secret_name", "secretRef"),
            ("secret_name", "secretRef"),
            ("sasl_type", "saslType"),
        ]:
            if kwargs.get(param_name):
                auth_settings[property_name] = kwargs[param_name]

        # lower the first letter of the authentication method
        auth_setting_name = authentication_method[0].lower() + authentication_method[1:] + "Settings"
        if auth_setting_name not in settings["authentication"]:
            settings["authentication"][auth_setting_name] = auth_settings
        else:
            settings["authentication"][auth_setting_name].update(auth_settings)

        return

    def _identify_authentication_method(
        self,
        no_auth: Optional[bool] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        scope: Optional[str] = None,
        sat_audience: Optional[str] = None,
        x509_secret_name: Optional[str] = None,
        sasl_type: Optional[str] = None,
        sasl_secret_name: Optional[str] = None,
        at_secret_name: Optional[str] = None,
        **_
    ) -> str:
        # Check for the presence of authentication-related parameters in kwargs
        if no_auth:
            return DataflowEndpointAuthenticationType.ANONYMOUS.value
        elif client_id or tenant_id or scope:
            return DataflowEndpointAuthenticationType.USERASSIGNED.value
        elif sat_audience:
            return DataflowEndpointAuthenticationType.SERVICEACCESSTOKEN.value
        elif x509_secret_name:
            return DataflowEndpointAuthenticationType.X509.value
        elif sasl_type or sasl_secret_name:
            return DataflowEndpointAuthenticationType.SASL.value
        elif at_secret_name:
            return DataflowEndpointAuthenticationType.ACCESSTOKEN.value
        else:
            return DataflowEndpointAuthenticationType.SYSTEMASSIGNED.value

    def _set_batching_settings(
        self,
        settings: dict,
        latency: Optional[int] = None,
        message_count: Optional[int] = None,
        batching_disabled: Optional[bool] = None,
        max_byte: Optional[int] = None,
        latency_ms: Optional[int] = None,
        **_
    ):
        if any([
            latency,
            message_count,
            batching_disabled,
            max_byte,
            latency_ms,
        ]):
            settings["batching"] = settings.get("batching", {})
            if latency:
                settings["batching"]["latencySeconds"] = latency
            if latency_ms:
                settings["batching"]["latencyMs"] = latency_ms
            if message_count:
                settings["batching"]["maxMessages"] = message_count
            if batching_disabled:
                settings["batching"]["mode"] = DataflowEndpointModeType.DISABLED.value \
                    if batching_disabled else DataflowEndpointModeType.ENABLED.value
            if max_byte:
                settings["batching"]["maxBytes"] = max_byte

    def _set_names_settings(
        self,
        settings: dict,
        lakehouse_name: Optional[str] = None,
        workspace_name: Optional[str] = None,
        **_
    ):
        if lakehouse_name or workspace_name:
            settings["names"] = settings.get("names", {})
            if lakehouse_name:
                settings["names"]["lakehouseName"] = lakehouse_name
            if workspace_name:
                settings["names"]["workspaceName"] = workspace_name

    def _set_tls_settings(
        self,
        settings: dict,
        endpoint_type: DataflowEndpointType,
        tls_disabled: Optional[bool] = None,
        config_map_reference: Optional[str] = None,
        **_
    ):
        if tls_disabled is not None or config_map_reference:
            settings["tls"] = settings.get("tls", {})
            if tls_disabled is not None:
                settings["tls"]["mode"] = DataflowEndpointModeType.DISABLED.value \
                    if tls_disabled else DataflowEndpointModeType.ENABLED.value
            if config_map_reference:
                settings["tls"]["trustedCaCertificateConfigMapRef"] = config_map_reference

        # for eventhub and eventgrid, tls mode is always enabled
        if endpoint_type in [
            DataflowEndpointType.EVENTHUB.value,
            DataflowEndpointType.EVENTGRID.value,
        ]:
            if settings.get("tls"):
                settings["tls"]["mode"] = DataflowEndpointModeType.ENABLED.value
            else:
                settings["tls"] = {"mode": DataflowEndpointModeType.ENABLED.value}

    def _process_endpoint_properties(
        self,
        endpoint_type: DataflowEndpointType,
        settings: dict,
        host: str,
        database_name: Optional[str] = None,
        path_type: Optional[str] = None,
        group_id: Optional[str] = None,
        copy_broker_props_disabled: Optional[bool] = None,
        compression: Optional[str] = None,
        acks: Optional[str] = None,
        partition_strategy: Optional[str] = None,
        cloud_event_attribute: Optional[str] = None,
        pvc_reference: Optional[str] = None,
        client_id_prefix: Optional[str] = None,
        protocol: Optional[str] = None,
        keep_alive: Optional[int] = None,
        retain: Optional[bool] = None,
        max_inflight_messages: Optional[int] = None,
        qos: Optional[int] = None,
        session_expiry: Optional[int] = None,
        **kwargs
    ):
        if host:
            settings["host"] = host
        if database_name:
            settings["database"] = database_name
        self._set_batching_settings(
            settings=settings,
            **kwargs
        )
        self._set_names_settings(settings=settings, **kwargs)
        if path_type:
            settings["oneLakePathType"] = path_type
        if group_id:
            settings["consumerGroupId"] = group_id
        if copy_broker_props_disabled:
            settings["copyMqttProperties"] = DataflowEndpointModeType.DISABLED.value \
                if copy_broker_props_disabled else DataflowEndpointModeType.ENABLED.value
        if compression:
            settings["compression"] = compression
        if acks:
            settings["kafkaAcks"] = acks
        if partition_strategy:
            settings["partitionStrategy"] = partition_strategy
        self._set_tls_settings(
            settings=settings,
            endpoint_type=endpoint_type,
            **kwargs
        )
        if cloud_event_attribute:
            settings["cloudEventAttributes"] = cloud_event_attribute
        if pvc_reference:
            settings["persistentVolumeClaimRef"] = pvc_reference
        if client_id_prefix:
            settings["clientIdPrefix"] = client_id_prefix
        if protocol:
            settings["protocol"] = protocol
        if keep_alive:
            settings["keepAliveSeconds"] = keep_alive
        if retain:
            settings["retain"] = retain
        if max_inflight_messages:
            settings["maxInflightMessages"] = max_inflight_messages
        if qos:
            settings["qos"] = qos
        if session_expiry:
            settings["sessionExpirySeconds"] = session_expiry

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
            kwargs.get("storage_account_name"),
            kwargs.get("eventhub_namespace"),
            kwargs.get("hostname"),
            kwargs.get("port")
        ]):
            host = self._get_endpoint_host(
                endpoint_type=endpoint_type,
                **kwargs
            )

            if host and host is not settings["host"]:
                settings["host"] = host

        if any([
            kwargs.get("authentication_type"),
            kwargs.get("client_id"),
            kwargs.get("tenant_id"),
            kwargs.get("scope"),
            kwargs.get("sami_audience"),
            kwargs.get("sat_audience"),
            kwargs.get("x509_secret_name"),
            kwargs.get("sasl_type"),
            kwargs.get("sasl_secret_name"),
            kwargs.get("at_secret_name"),
            kwargs.get("no_auth"),
        ]):
            self._process_authentication_type(
                endpoint_type=endpoint_type,
                settings=settings,
                **kwargs
            )

        # Preventing host parameter from duplication
        if settings.get("host") and "host" in kwargs:
            del kwargs["host"]

        self._process_endpoint_properties(
            endpoint_type=endpoint_type,
            settings=settings,
            host=settings.get("host"),
            **kwargs
        )
