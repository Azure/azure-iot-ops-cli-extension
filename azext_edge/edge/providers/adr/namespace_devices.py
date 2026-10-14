# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    ResourceNotFoundError,
)
from knack.log import get_logger
from rich.console import Console

from ...common import ListableEnum
from .common import EndpointTemplateMode
from ...util.az_client import (
    get_registry_mgmt_client,
    wait_for_terminal_state,
)
from ...util.common import parse_kvp_nargs, should_continue_prompt
from ...util.id_tools import parse_resource_id
from ...util.queryable import Queryable
from ..orchestration.resources.connector_templates import ConnectorTemplates

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt.operations import (
        NamespaceDevicesOperations,
        NamespacesOperations,
    )


console = Console()
logger = get_logger(__name__)
NAMESPACE_DEVICE_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces/devices"
# Draft-07 is the only dialect supported for CLI-side config validation.
# Schemas with other dialects are still accepted — validation is skipped with a warning.
_ENDPOINT_SCHEMA_DRAFT_URI = "http://json-schema.org/draft-07/schema#"


class DeviceEndpointType(ListableEnum):
    """
    Enum for the device endpoint types.
    """

    OPCUA = "Microsoft.OpcUa"
    ONVIF = "Microsoft.Onvif"
    MEDIA = "Microsoft.Media"
    REST = "Microsoft.Http"
    SSE = "Microsoft.SSEHttp"
    MQTT = "Microsoft.Mqtt"

    @classmethod
    def get_type_from_keyword(cls, keyword: str, return_custom_keyword: bool = True) -> Optional[str]:
        """
        Returns the endpoint type based on the keyword.

        For listing endpoint purposes, if the keyword does not match any known type, it will return
        the keyword itself.
        For testing purposes, if the keyword does not match any known type, it will return "custom".
        """
        mapped_types = {
            "opcua": cls.OPCUA.value,
            "onvif": cls.ONVIF.value,
            "media": cls.MEDIA.value,
            "rest": cls.REST.value,
            "sse": cls.SSE.value,
            "mqtt": cls.MQTT.value
        }
        return mapped_types.get(keyword.lower(), "custom" if return_custom_keyword else keyword)


class NamespaceDevices(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_mgmt_client(
            **self._get_client_kwargs()
        )
        self.ops: "NamespaceDevicesOperations" = self.deviceregistry_mgmt_client.namespace_devices
        self.namespace_ops: "NamespacesOperations" = self.deviceregistry_mgmt_client.namespaces

    def create(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        custom_attributes: Optional[List[str]] = None,
        disabled: Optional[bool] = None,
        instance_subscription: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        operating_system: Optional[str] = None,
        operating_system_version: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        # get the extended location from the instance
        from .helpers import get_extended_location, strip_nulls
        extended_location = get_extended_location(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            instance_subscription=instance_subscription
        )
        # use the namespace location instead of the cluster location
        extended_location.pop("cluster_location")

        namespace = extended_location.pop("namespace", None)
        if not namespace:
            raise InvalidArgumentValueError(
                "The instance must have an ADR namespace reference to create a namespaced device."
            )
        # get the location of the namespace
        location = self.namespace_ops.get(
            resource_group_name=namespace["resource_group"],
            namespace_name=namespace["name"]
        )["location"]

        device_body = {
            "extendedLocation": extended_location,
            "location": location,
            "properties": strip_nulls({
                "attributes": parse_kvp_nargs(custom_attributes),
                "enabled": not disabled,
                "manufacturer": manufacturer,
                "model": model,
                "operatingSystem": operating_system,
                "operatingSystemVersion": operating_system_version
            }),
            "tags": tags
        }

        with console.status(f"Creating {device_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                resource=device_body
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        confirm_yes: bool = False,
        **kwargs
    ):
        # should bail prompt
        if not should_continue_prompt(confirm_yes):
            return

        from .helpers import get_namespace_for_instance
        namespace = get_namespace_for_instance(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )

        with console.status(f"Deleting {device_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(
        self,
        device_name: str,
        resource_group: str,
        namespace_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        check_cluster: bool = False
    ) -> dict:
        """
        Shows the details of a device in a namespace.
        One of the `namespace_name` or `instance_name` must be provided.

        Resource group can be either the namespace resource group or the instance resource group.
        The expected behavior is that if `namespace_name` is provided, the resource group
        is the namespace resource group, and if `instance_name` is provided, the resource group
        is the instance resource group."""
        if not namespace_name:
            # assume resource group is instance resource group
            from .helpers import get_namespace_for_instance
            namespace = get_namespace_for_instance(
                cmd=self.cmd,
                instance_name=instance_name,
                instance_resource_group=resource_group
            )
            namespace_name = namespace["name"]
            resource_group = namespace["resource_group"]

        device = self.ops.get(
            resource_group_name=resource_group, namespace_name=namespace_name, device_name=device_name
        )

        if check_cluster:
            from .helpers import check_cluster_connectivity
            check_cluster_connectivity(self.cmd, device)
        return device

    def query_devices(
        self,
        device_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        instance_resource_group: Optional[str] = None,
        disabled: Optional[bool] = None,
        custom_query: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        operating_system: Optional[str] = None,
        operating_system_version: Optional[str] = None,
    ) -> dict:
        """
        Queries the devices using Azure Resource Graph.
        """
        from .helpers import get_instance_query, get_query
        query = "Resources | where type =~ '{}'".format(NAMESPACE_DEVICE_RESOURCE_TYPE)

        # for now, keep it simple
        # ideas for later on, add namespace (needs id parsing), endpoint types (will need to add joins)
        def _build_query_body(
            **params: dict
        ) -> str:
            param_mapping = {
                "device_name": "name",
                "manufacturer": "properties.manufacturer",
                "model": "properties.model",
                "operating_system": "properties.operatingSystem",
                "operating_system_version": "properties.operatingSystemVersion",
            }
            return get_query(
                param_mapping=param_mapping,
                params=params,
            )

        query += custom_query or _build_query_body(
            device_name=device_name,
            disabled=disabled,
            manufacturer=manufacturer,
            model=model,
            operating_system=operating_system,
            operating_system_version=operating_system_version
        )

        query = get_instance_query(
            query=query,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )
        logger.info(f"Querying devices with query: {query}")
        return self.query(query=query)

    def update(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        custom_attributes: Optional[List[str]] = None,
        disabled: Optional[bool] = None,
        operating_system_version: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        from .helpers import get_namespace_for_instance
        namespace = get_namespace_for_instance(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )
        update_payload = {
            "properties": {}
        }
        if tags:
            update_payload["tags"] = tags
        if custom_attributes:
            update_payload["properties"]["attributes"] = parse_kvp_nargs(custom_attributes)
        if disabled is not None:
            update_payload["properties"]["enabled"] = not disabled
        if operating_system_version:
            update_payload["properties"]["operatingSystemVersion"] = operating_system_version

        # remove the properties key if there are no properties to update
        if not update_payload["properties"]:
            update_payload.pop("properties")

        with console.status(f"Updating {device_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                device_name=device_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )

    def add_inbound_endpoint(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        endpoint_name: str,
        endpoint_address: str,
        endpoint_type: str,
        endpoint_version: Optional[str] = None,
        certificate_reference: Optional[str] = None,
        key_reference: Optional[str] = None,
        intermediate_certificate_reference: Optional[str] = None,
        password_reference: Optional[str] = None,
        username_reference: Optional[str] = None,
        trust_list: Optional[str] = None,
        replace: Optional[bool] = False,
        is_custom_command: bool = False,
        **kwargs
    ):
        from .helpers import process_additional_configuration, process_authentication

        # Set version from connector template if not provided by user
        if endpoint_version is None:
            connector_templates = ConnectorTemplates(cmd=self.cmd)
            endpoint_version = connector_templates.get_endpoint_version_for_type(
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_type=endpoint_type,
                is_custom_command=is_custom_command,
            )

        # get the original inbound endpoints
        device = self.show(
            device_name=device_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        namespace = parse_resource_id(device["id"])
        original_endpoints = _get_endpoints(device)
        if endpoint_name in original_endpoints and not replace:
            raise InvalidArgumentValueError(
                f"Inbound endpoint '{endpoint_name}' already exists. Use --replace to update it."
            )

        # create the new endpoint
        endpoint_body = {
            "address": endpoint_address,
            "endpointType": endpoint_type,
            "version": endpoint_version,
            "authentication": process_authentication(
                certificate_reference=certificate_reference,
                key_reference=key_reference,
                intermediate_certificate_reference=intermediate_certificate_reference,
                password_reference=password_reference,
                username_reference=username_reference
            )
        }

        # process the configuration for the endpoint
        config_func = ENDPOINT_TYPE_TO_FUNCTION_MAP.get(endpoint_type, process_additional_configuration)
        if config_func:
            endpoint_body["additionalConfiguration"] = config_func(**kwargs)

        # trust settings
        if trust_list:
            endpoint_body["trustSettings"] = {
                "trustList": trust_list
            }

        # update the endpoints with the new one
        original_endpoints[endpoint_name] = endpoint_body

        # update payload
        update_payload = {
            "properties": {
                "endpoints": {
                    "inbound": original_endpoints
                }
            }
        }

        with console.status(f"Updating inbound endpoints for {device_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            result = self.show(
                device_name=device_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"]
            )
            return result["properties"].get("endpoints", {}).get("inbound", {})

    def _handle_show_template(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        template_mode: str,
        endpoint_config: Optional[str],
    ) -> dict:
        """Return a config/schema template for --show-template and exit early.

        OPC UA uses bundled metadata; all other types fetch the connector template from ACR.
        ValidationError (OPC UA explicitly Disabled) intentionally propagates; ARM 404s fall
        back to the bundled metadata so offline / test callers still get a useful response.
        """
        if endpoint_config:
            raise InvalidArgumentValueError(
                "--show-template and --endpoint-config cannot be used together. "
                "--show-template displays the template and exits without creating an endpoint."
            )
        is_opcua = connector_type.lower() == DeviceEndpointType.OPCUA.value.lower()
        if is_opcua:
            from azure.core.exceptions import ResourceNotFoundError as _AzureNotFoundError

            opcua_metadata = None
            if instance_name and instance_resource_group:
                try:
                    from .helpers import get_opcua_info as _get_opcua_info
                    opcua_metadata = _get_opcua_info(self.cmd, instance_name, instance_resource_group)
                except _AzureNotFoundError:
                    pass  # instance / resource-group not found – use bundled metadata
            if opcua_metadata is None:
                from .helpers import load_opcua_metadata_file
                opcua_metadata = load_opcua_metadata_file()
            schema = {}
            for ep in opcua_metadata.get("inboundEndpoints", []):
                if ep.get("endpointType", "").lower() == DeviceEndpointType.OPCUA.value.lower():
                    schema = ep.get("additionalConfigurationSchema", {})
                    break
            slim_warnings: List[str] = []
            from .helpers import _slim_schema, _consolidate_warnings
            slimmed = _slim_schema(schema, mode=template_mode, _warnings=slim_warnings)
            for w in _consolidate_warnings(slim_warnings):
                logger.warning(w)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(slimmed, dict):
                slimmed.pop("$id", None)
            return {"connectorType": connector_type, "endpointConfig": slimmed}

        connector_templates = ConnectorTemplates(cmd=self.cmd)
        raw = connector_templates.get_endpoint_schema(
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            connector_type=connector_type,
        )
        if isinstance(raw, dict) and "endpointConfig" in raw:
            slim_warnings = []
            from .helpers import _slim_schema, _consolidate_warnings
            raw["endpointConfig"] = _slim_schema(raw["endpointConfig"], mode=template_mode, _warnings=slim_warnings)
            for w in _consolidate_warnings(slim_warnings):
                logger.warning(w)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(raw["endpointConfig"], dict):
                raw["endpointConfig"].pop("$id", None)
        return raw

    def _resolve_connector_version(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        endpoint_version: Optional[str],
        skip_connector_check: bool,
        is_opcua: bool,
    ) -> Optional[str]:
        """Verify connector availability and auto-resolve the endpoint version.

        OPC UA: verifies the feature is enabled; version is left as None (ADR manages it).
        Custom/3P: looks up the connector template and resolves version from it when not supplied.
        Returns unchanged endpoint_version (possibly None) when skip_connector_check is True.
        """
        if skip_connector_check:
            return endpoint_version

        if is_opcua:
            from .helpers import get_opcua_info as _get_opcua_info
            _get_opcua_info(self.cmd, instance_name, instance_resource_group)
            return endpoint_version  # None — let ADR manage the OPC UA endpoint version

        connector_templates = ConnectorTemplates(cmd=self.cmd)
        template = connector_templates.get_connector_template_for_type(
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            connector_type=connector_type,
        )
        if template is None:
            raise ResourceNotFoundError(
                f"No connector template found for connector type '{connector_type}' "
                f"in instance '{instance_name}'.\n"
                "Create one with: az iot ops connector template create ..."
            )
        if endpoint_version is None:
            endpoint_version = connector_templates.get_endpoint_version_for_type(
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                endpoint_type=connector_type,
            )
        return endpoint_version

    def _load_and_validate_endpoint_config(
        self,
        endpoint_config: str,
        connector_type: str,
        is_opcua: bool,
        skip_connector_check: bool,
        instance_name: str,
        instance_resource_group: str,
    ) -> str:
        """Load endpoint config from a file path or inline JSON and validate it against schema.

        Validation is only performed when skip_connector_check is False and the connector's
        additionalConfigurationSchema uses JSON Schema Draft-07.  Other dialects are accepted
        but validation is skipped with a warning.  Returns the serialized JSON string.
        """
        from .helpers import process_additional_configuration

        additional_configuration = process_additional_configuration(
            additional_configuration=endpoint_config,
            config_type="endpoint",
        )

        # Auto-unwrap if the user passed --show-template output directly.
        # That output is a dict with 'connectorType' and 'endpointConfig' keys;
        # --endpoint-config expects only the inner endpointConfig value.
        _parsed = json.loads(additional_configuration)
        if isinstance(_parsed, dict) and "endpointConfig" in _parsed:
            provided = _parsed.get("connectorType")
            if provided and connector_type and provided.lower() != connector_type.lower():
                raise InvalidArgumentValueError(
                    f"Config connectorType '{provided}' does not match endpoint connectorType '{connector_type}'."
                )
            additional_configuration = json.dumps(_parsed["endpointConfig"])

        if skip_connector_check:
            return additional_configuration

        if is_opcua:
            from .specs import NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA as _endpoint_schema
        else:
            connector_templates = ConnectorTemplates(cmd=self.cmd)
            _endpoint_schema = connector_templates.get_endpoint_schema(
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                connector_type=connector_type,
            ).get("endpointConfig", {})
            if not _endpoint_schema:
                from azure.cli.core.azclierror import ValidationError

                raise ValidationError(
                    f"Schema retrieval failed for connector type '{connector_type}'. "
                    "Endpoint config validation cannot proceed. "
                    "Rerun with --skip-connector-check to bypass validation."
                )

        if _endpoint_schema:
            from ...util.schema_validation import check_json_schema, validate_data_against_schema

            skip_reason = check_json_schema(_endpoint_schema)
            if skip_reason:
                logger.warning("Skipping endpoint config validation: %s", skip_reason)
            elif _endpoint_schema.get("$schema", "") not in ("", _ENDPOINT_SCHEMA_DRAFT_URI):
                logger.warning(
                    "Skipping endpoint config validation: schema dialect '%s' is not supported; "
                    "only '%s' is accepted.",
                    _endpoint_schema["$schema"],
                    _ENDPOINT_SCHEMA_DRAFT_URI,
                )
            else:
                # Strip null values before validation — null means "not provided" for optional fields.
                # The --show-template config output uses null as a placeholder for fields with no default.
                from .helpers import strip_nulls
                config_data = strip_nulls(json.loads(additional_configuration))
                validate_data_against_schema(
                    _endpoint_schema,
                    config_data,
                    name="endpoint",
                )

        return additional_configuration

    def apply_inbound_endpoint_by_connector_type(
        self,
        instance_name: str,
        instance_resource_group: str,
        connector_type: str,
        device_name: Optional[str] = None,
        endpoint_name: Optional[str] = None,
        endpoint_address: Optional[str] = None,
        endpoint_config: Optional[str] = None,
        show_template: Optional[str] = None,
        skip_connector_check: bool = False,
        endpoint_version: Optional[str] = None,
        certificate_reference: Optional[str] = None,
        key_reference: Optional[str] = None,
        intermediate_certificate_reference: Optional[str] = None,
        password_reference: Optional[str] = None,
        username_reference: Optional[str] = None,
        trust_list: Optional[str] = None,
        no_replace: Optional[bool] = False,
        **kwargs
    ):
        """Generalized command for adding an inbound device endpoint using a connector type.

        Supports template discovery (--show-template) and inline JSON or file-based endpoint
        configuration (--endpoint-config) driven by the connector template metadata.

        OPC UA (Microsoft.OpcUa) is handled separately: it does not use Akri connector
        templates. Its metadata (including version and schema) is bundled locally.
        """
        from .helpers import process_authentication

        is_opcua = connector_type.lower() == DeviceEndpointType.OPCUA.value.lower()

        if show_template:
            return self._handle_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                endpoint_config=endpoint_config,
            )

        # Provider-level required arg guards (CLI enforces these too, but provider
        # may be called directly in tests or other code paths).
        from azure.cli.core.azclierror import RequiredArgumentMissingError
        if not device_name:
            raise RequiredArgumentMissingError("--device is required.")
        if not endpoint_name:
            raise RequiredArgumentMissingError("--name is required.")
        if not endpoint_address:
            raise RequiredArgumentMissingError("--endpoint-address is required.")

        # Validate auth args against 1P connector type capabilities.
        # Custom connector types are skipped — the user is responsible for knowing what their connector supports.
        _validate_auth_args_for_connector_type(
            connector_type=connector_type,
            certificate_reference=certificate_reference,
            key_reference=key_reference,
            intermediate_certificate_reference=intermediate_certificate_reference,
            trust_list=trust_list,
        )

        if skip_connector_check and endpoint_config:
            raise InvalidArgumentValueError(
                "--skip-connector-check cannot be used when --endpoint-config is provided.\n"
                "Create or verify a connector template first: az iot ops connector template create ..."
            )

        endpoint_version = self._resolve_connector_version(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            endpoint_version=endpoint_version,
            skip_connector_check=skip_connector_check,
            is_opcua=is_opcua,
        )

        additional_configuration = None
        if endpoint_config:
            additional_configuration = self._load_and_validate_endpoint_config(
                endpoint_config=endpoint_config,
                connector_type=connector_type,
                is_opcua=is_opcua,
                skip_connector_check=skip_connector_check,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )

        endpoint_body = {
            "address": endpoint_address,
            "endpointType": connector_type,
            "version": endpoint_version,
            "authentication": process_authentication(
                certificate_reference=certificate_reference,
                key_reference=key_reference,
                intermediate_certificate_reference=intermediate_certificate_reference,
                password_reference=password_reference,
                username_reference=username_reference,
            ),
        }

        if additional_configuration is not None:
            endpoint_body["additionalConfiguration"] = additional_configuration

        if trust_list:
            endpoint_body["trustSettings"] = {"trustList": trust_list}

        device = self.show(
            device_name=device_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        namespace = parse_resource_id(device["id"])
        original_endpoints = _get_endpoints(device)

        if endpoint_name in original_endpoints and no_replace:
            raise InvalidArgumentValueError(
                f"Inbound endpoint '{endpoint_name}' already exists. "
                "Use the default apply behavior (omit --no-replace) to allow updates."
            )

        original_endpoints[endpoint_name] = endpoint_body

        update_payload = {
            "properties": {
                "endpoints": {
                    "inbound": original_endpoints
                }
            }
        }

        with console.status(f"Updating inbound endpoints for {device_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            result = self.show(
                device_name=device_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return result["properties"].get("endpoints", {}).get("inbound", {})

    def list_endpoints(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        inbound: bool = False,
        inbound_endpoint_type: Optional[str] = None
    ) -> dict:
        device = self.show(
            device_name=device_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        endpoints = _get_endpoints(device, inbound=inbound)
        if inbound and inbound_endpoint_type:
            # support inputs of just "opcua", "onvif", etc.
            inbound_endpoint_type = DeviceEndpointType.get_type_from_keyword(
                inbound_endpoint_type, return_custom_keyword=False
            )
            endpoints = {
                name: body for name, body in endpoints.items()
                if body.get("endpointType", "").lower() == inbound_endpoint_type.lower()
            }
        return endpoints

    def inbound_remove_endpoint(
        self,
        device_name: str,
        instance_name: str,
        instance_resource_group: str,
        endpoint_names: List[str],
        confirm_yes: bool = False,
        **kwargs
    ):
        # should bail prompt
        if not should_continue_prompt(confirm_yes):
            return

        # get the original inbound endpoints
        device = self.show(
            device_name=device_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        namespace = parse_resource_id(device["id"])
        original_endpoints = _get_endpoints(device)
        # remove the endpoints from the endpoint list by key
        # only send endpoints to be removed with null values
        # also include any existing endpoints that already have null bodies
        endpoints_to_remove = {}

        # Add endpoints explicitly requested for removal
        for endpoint_name in endpoint_names:
            if endpoint_name in original_endpoints:
                endpoints_to_remove[endpoint_name] = None

        # Add any existing endpoints that already have null/None bodies
        for endpoint_name, endpoint_body in original_endpoints.items():
            if endpoint_body is None:
                endpoints_to_remove[endpoint_name] = None

        # update payload
        update_payload = {
            "properties": {
                "endpoints": {
                    "inbound": endpoints_to_remove
                }
            }
        }

        with console.status(f"Updating inbound endpoints for {device_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            result = self.show(
                device_name=device_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"]
            )
            return result["properties"].get("endpoints", {}).get("inbound", {})


def _get_endpoints(device: dict, inbound: bool = True) -> dict:
    """
    Helper function to extract endpoints from a device.
    """
    device_props = device["properties"]

    # if device.properties.endpoints is not present or empty,
    # both inbound and outbound endpoints are {}
    if "endpoints" not in device_props or not device_props["endpoints"]:
        return {}

    device_endpoints = device_props.get("endpoints", {})
    return device_endpoints.get("inbound", {}) if inbound else device_endpoints


# Connector types that do NOT support certificate-based authentication.
_NO_CERT_AUTH_TYPES = {
    DeviceEndpointType.MEDIA.value.lower(),
    DeviceEndpointType.ONVIF.value.lower(),
}


def _validate_auth_args_for_connector_type(
    connector_type: str,
    certificate_reference: Optional[str] = None,
    key_reference: Optional[str] = None,
    intermediate_certificate_reference: Optional[str] = None,
    trust_list: Optional[str] = None,
) -> None:
    """
    Raises an error if cert-based auth args are used with a connector type that doesn't support them.
    Only Media and Onvif lack cert support. Custom/unknown types are skipped.
    """
    if connector_type.lower() not in _NO_CERT_AUTH_TYPES:
        return

    cert_args_used = [
        arg for arg, val in [
            ("--cert-ref", certificate_reference),
            ("--key-ref", key_reference),
            ("--icr", intermediate_certificate_reference),
            ("--trust-list", trust_list),
        ] if val
    ]

    if cert_args_used:
        raise InvalidArgumentValueError(
            f"Certificate-based authentication ({', '.join(cert_args_used)}) is not supported "
            f"for connector type '{connector_type}'.\n"
            f"Only username/password authentication is supported for this connector type."
        )


def _process_onvif_configuration(
    accept_invalid_hostnames: Optional[bool] = False,
    accept_invalid_certificates: Optional[bool] = False,
    fallback_to_username_token_auth: Optional[bool] = False,
    **_
) -> str:
    """
    Creates a stringified JSON that follows the ONVIF endpoint schema specifications
    defined in NAMESPACE_DEVICE_ONVIF_ENDPOINT_SCHEMA.
    """
    configuration = {
        "acceptInvalidHostnames": accept_invalid_hostnames,
        "acceptInvalidCertificates": accept_invalid_certificates,
        "fallbackToUsernameTokenAuth": fallback_to_username_token_auth
    }

    return json.dumps(configuration)


def _process_opcua_configuration(
    application_name: Optional[str] = "OPC UA Broker",
    keep_alive: Optional[int] = 10000,
    publishing_interval: Optional[int] = 1000,
    sampling_interval: Optional[int] = 1000,
    queue_size: Optional[int] = 1,
    key_frame_count: Optional[int] = 0,
    session_timeout: Optional[int] = 60000,
    session_keep_alive_interval: Optional[int] = 10000,
    session_reconnect_period: Optional[int] = 2000,
    session_reconnect_exponential_backoff: Optional[int] = 10000,
    session_enable_tracing_headers: Optional[bool] = False,
    subscription_max_items: Optional[int] = 1000,
    subscription_life_time: Optional[int] = 60000,
    security_auto_accept_certificates: Optional[bool] = False,
    security_policy: Optional[str] = None,
    security_mode: Optional[str] = None,
    run_asset_discovery: Optional[bool] = False,
    sync_properties_into_state_store: Optional[bool] = False,
    shared: Optional[bool] = False,
    **_
) -> str:
    """
    Creates a stringified JSON that follows the OPC UA endpoint schema specifications
    defined in NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA.
    """
    from .helpers import ensure_schema_structure
    from .specs import NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA

    if security_policy:
        security_policy = "http://opcfoundation.org/UA/SecurityPolicy#" + security_policy

    configuration = {
        "applicationName": application_name,
        "keepAliveMilliseconds": keep_alive,
        "defaults": {
            "publishingIntervalMilliseconds": publishing_interval,
            "samplingIntervalMilliseconds": sampling_interval,
            "queueSize": queue_size,
            "keyFrameCount": key_frame_count
        },
        "session": {
            "timeoutMilliseconds": session_timeout,
            "keepAliveIntervalMilliseconds": session_keep_alive_interval,
            "reconnectPeriodMilliseconds": session_reconnect_period,
            "reconnectExponentialBackOffMilliseconds": session_reconnect_exponential_backoff,
            "enableTracingHeaders": session_enable_tracing_headers
        },
        "subscription": {
            "maxItems": subscription_max_items,
            "lifeTimeMilliseconds": subscription_life_time
        },
        "security": {
            "autoAcceptUntrustedServerCertificates": security_auto_accept_certificates,
            "securityPolicy": security_policy,
            "securityMode": security_mode
        },
        "runAssetDiscovery": run_asset_discovery,
        "syncPropertiesIntoStateStore": sync_properties_into_state_store,
        "shared": shared
    }

    # Validate the configuration against the schema
    ensure_schema_structure(NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA, configuration)

    return json.dumps(configuration)


def _process_mqtt_configuration(
    asset_level: Optional[int] = 1,
    topic_filter: Optional[str] = None,
    topic_mapping_prefix: Optional[str] = None,
    **_
) -> str:
    """
    Creates a stringified JSON for the MQTT endpoint configuration.
    """
    configuration: Dict = {
        "assetLevel": asset_level,
    }
    if topic_filter is not None:
        configuration["topicFilter"] = topic_filter
    if topic_mapping_prefix is not None:
        configuration["topicMappingPrefix"] = topic_mapping_prefix

    return json.dumps(configuration)


ENDPOINT_TYPE_TO_FUNCTION_MAP: Dict[str, Optional[Callable]] = {
    DeviceEndpointType.OPCUA.value: _process_opcua_configuration,
    DeviceEndpointType.ONVIF.value: _process_onvif_configuration,
    DeviceEndpointType.MEDIA.value: None,
    DeviceEndpointType.MQTT.value: _process_mqtt_configuration,
}
