# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Iterable, Optional

from knack.log import get_logger
from rich.console import Console

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
        source_endpoint_obj = self._process_exist_endpoint(
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

        # when Kafka endpoint, validate consumer group id
        if source_endpoint_type == DataflowEndpointType.KAFKA.value:
            group_id = source_endpoint_obj.get("properties", {}).get("kafkaSettings", {}).get("consumerGroupId", "")
            if not group_id:
                raise InvalidArgumentValueError(
                    "'consumerGroupId' is required in kafka source dataflow endpoint configuration."
                )

        # get destination endpoint
        desination_endpoint_obj = self._process_exist_endpoint(
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
                f"'schemaRef' is required for dataflow due to destination endpoint '{destination_endpoint_type}' type."
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
                "Either source or destination endpoint must be Azure IoT Operations Local "
                f"MQTT endpoint with host containing '{LOCAL_MQTT_HOST_PREFIX}'."
            )

    def _process_exist_endpoint(
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
