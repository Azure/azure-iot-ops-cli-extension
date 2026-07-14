# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

from azure.cli.core.azclierror import (
    CLIInternalError,
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
    ValidationError,
)
from knack.log import get_logger
from rich.console import Console

from ...util.az_client import (
    get_registry_mgmt_client,
    get_resource_client,
    wait_for_terminal_state
)
from ...util import dump_content_to_file
from ...util.common import parse_kvp_nargs, should_continue_prompt
from ...util.id_tools import parse_resource_id
from ...util.queryable import Queryable
from .common import FileType
from .helpers import (
    check_cluster_connectivity,
    ensure_schema_structure,
    get_instance_query,
    get_namespace_for_instance,
    get_query,
    process_additional_configuration,
)
from .namespace_devices import DeviceEndpointType
from .validator import ConnectorMetadataValidator

if TYPE_CHECKING:
    from ...vendor.clients.deviceregistrymgmt.operations import (
        NamespaceAssetsOperations,
        NamespaceDevicesOperations,
    )
    from ...vendor.clients.resourcesmgmt.operations import ResourcesOperations


console = Console()
logger = get_logger(__name__)
NAMESPACE_ASSET_RESOURCE_TYPE = "Microsoft.DeviceRegistry/namespaces/assets"


def _convert_sub_points_to_csv_namespace(
    sub_points: List[Dict[str, str]],
    sub_point_type: str,
    default_configuration: str,
    portal_friendly: bool = False
) -> List[str]:
    """Convert datapoints or events to CSV format. Modifies sub_points in-place."""
    from collections import OrderedDict

    csv_conversion_map = [
        ("queueSize", "QueueSize" if portal_friendly else "Queue Size"),
        ("observabilityMode", "ObservabilityMode" if portal_friendly else "Observability Mode"),
    ]

    if not portal_friendly or sub_point_type == "dataPoints":
        csv_conversion_map.append(("samplingInterval", "Sampling Interval Milliseconds"))
    if not portal_friendly:
        csv_conversion_map.append(("capabilityId", "Capability Id"))

    if sub_point_type == "dataPoints":
        csv_conversion_map.insert(0, ("dataSource", "NodeID" if portal_friendly else "Data Source"))
        csv_conversion_map.insert(1, ("name", "TagName" if portal_friendly else "Name"))
    else:
        csv_conversion_map.insert(0, ("dataSource", "Data Source"))
        csv_conversion_map.insert(1, ("name", "EventName" if portal_friendly else "Name"))

    csv_conversion_map = OrderedDict(csv_conversion_map)
    default_config = json.loads(default_configuration) if portal_friendly else {}

    for point in sub_points:
        config_key = f"{sub_point_type[:-1]}Configuration"
        configuration = point.pop(config_key, "{}")
        point.update(json.loads(configuration))

        if portal_friendly:
            point.pop("capabilityId", None)
            if sub_point_type == "events":
                point.pop("samplingInterval", None)

        for asset_key, csv_key in csv_conversion_map.items():
            point[csv_key] = point.pop(asset_key, default_config.get(asset_key))

    return list(csv_conversion_map.values())


def _convert_sub_points_from_csv_namespace(sub_points: List[Dict[str, str]]):
    """Convert CSV format back to JSON. Modifies sub_points in-place."""
    csv_conversion_map = {
        "CapabilityId": "capabilityId",
        "Capability Id": "capabilityId",
        "Data Source": "dataSource",
        "EventName": "name",
        "EventNotifier": "eventNotifier",
        "Event Notifier": "eventNotifier",
        "Name": "name",
        "NodeID": "dataSource",
        "ObservabilityMode": "observabilityMode",
        "Observability Mode": "observabilityMode",
        "QueueSize": "queueSize",
        "Queue Size": "queueSize",
        "Sampling Interval Milliseconds": "samplingInterval",
        "TagName": "name",
    }

    for point in sub_points:
        point.pop("", None)

        for csv_key, json_key in csv_conversion_map.items():
            if csv_key in point:
                point[json_key] = point.pop(csv_key)

        configuration = {}
        # Move observabilityMode to configuration if it exists and is not empty
        observability_value = point.pop("observabilityMode", None)
        if observability_value and observability_value.strip():
            configuration["observabilityMode"] = observability_value.strip().capitalize()

        # Move samplingInterval to configuration if it exists and is not empty
        sampling_value = point.pop("samplingInterval", None)
        if sampling_value and str(sampling_value).strip():
            configuration["samplingInterval"] = int(sampling_value)

        # Move queueSize to configuration if it exists and is not empty
        queue_value = point.pop("queueSize", None)
        if queue_value and str(queue_value).strip():
            configuration["queueSize"] = int(queue_value)

        if configuration:
            config_key = "dataPointConfiguration" if "dataSource" in point else "eventConfiguration"
            point[config_key] = json.dumps(configuration)


def _convert_actions_to_csv(actions: List[Dict[str, str]]) -> List[str]:
    """Convert actions to CSV format. Modifies actions in-place and returns fieldnames."""
    # CSV column order per DOE design
    fieldnames = ["name", "targetUri", "actionType", "topic", "timeoutInSeconds"]

    for action in actions:
        # Ensure all standard fields are present (empty string if missing)
        for field in fieldnames:
            if field not in action:
                action[field] = ""
            elif action[field] is None:
                action[field] = ""

    return fieldnames


def _convert_actions_from_csv(actions: List[Dict[str, str]]):
    """Convert CSV format back to action objects. Modifies actions in-place."""
    # Only map CSV column names that differ from JSON property names
    csv_to_json_map = {
        "Name": "name",
        "Target URI": "targetUri",
        "Action Type": "actionType",
        "Topic": "topic",
        "Timeout Seconds": "timeoutInSeconds",
    }

    for action in actions:
        action.pop("", None)

        # Map alternate CSV column names to JSON property names
        for csv_key, json_key in csv_to_json_map.items():
            if csv_key in action:
                action[json_key] = action.pop(csv_key)

        # Convert timeoutInSeconds to integer if present and non-empty
        timeout_value = action.get("timeoutInSeconds")
        if timeout_value and str(timeout_value).strip():
            try:
                action["timeoutInSeconds"] = int(timeout_value)
            except ValueError:
                pass  # Let validation catch invalid values
        elif "timeoutInSeconds" in action:
            del action["timeoutInSeconds"]

        # Remove empty optional fields
        for field in ["topic", "actionType", "typeRef"]:
            if field in action and (action[field] is None or action[field] == ""):
                del action[field]


class NamespaceAssets(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.deviceregistry_mgmt_client = get_registry_mgmt_client(
            **self._get_client_kwargs()
        )
        self.resource_mgmt_client = get_resource_client(
            **self._get_client_kwargs()
        )
        self.ops: "NamespaceAssetsOperations" = self.deviceregistry_mgmt_client.namespace_assets
        self.device_ops: "NamespaceDevicesOperations" = self.deviceregistry_mgmt_client.namespace_devices
        self.resource_ops: "ResourcesOperations" = self.resource_mgmt_client.resources

    def _validate_imported_items(
        self,
        items: List[dict],
        validate_fn,
        resource_label: str,
        asset: dict,
        instance_name: str,
        instance_resource_group: str,
    ):
        """Run connector-metadata validation on items, with graceful fallback.

        Metadata fetch/schema failures (e.g. connector metadata with fields not yet recognised by
        the bundled schema) are treated as warnings so import can proceed. Only item-level
        ValidationErrors (user data does not conform to the connector's own schema) are hard errors.
        """
        try:
            validator = ConnectorMetadataValidator.from_asset(
                cmd=self.cmd,
                asset=asset,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
        except Exception as e:
            logger.warning(
                f"{resource_label} validation skipped: could not load connector metadata ({e}). "
                "This can occur when the connector metadata version is ahead of the bundled schema "
                "or the cluster is not reachable. "
                f"The {resource_label.lower()} will be imported but may fail at runtime.",
                exc_info=True,
            )
            return

        try:
            for item in items:
                validate_fn(validator, item)
            logger.info(f"{resource_label} validated successfully.")
        except ValidationError:
            raise
        except Exception as e:
            logger.warning(
                f"{resource_label} validation skipped: {e}. "
                f"The {resource_label.lower()} will be imported but may fail at runtime."
            )

    def create(  # noqa: C901
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        device_name: str,
        device_endpoint_name: str,
        asset_type_refs: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None,
        description: Optional[str] = None,
        disabled: Optional[bool] = None,
        discovered_asset_refs: Optional[List[str]] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> dict:
        """Creates a new asset in the specified namespace.

        kwargs will contain arguments used for default configurations and destinations.
        """
        # TODO: future, Add in options to import from files for datasets, events, streams, and mgmt groups

        # use the device to get the location, extended location, and check type and endpoint
        device, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            device_name=device_name,
            device_endpoint_name=device_endpoint_name
        )

        # Initialize properties dictionary
        properties = {
            "deviceRef": {
                "deviceName": device_name,
                "endpointName": device_endpoint_name
            }
        }

        # handle the configs + destinations
        config_destinations = _process_configs(
            asset_type=asset_type,
            **kwargs
        )
        # might need to do some processing in the future
        properties.update(config_destinations)

        # other props
        _update_asset_props(
            properties=properties,
            asset_type_refs=asset_type_refs,
            attributes=attributes,
            description=description,
            disabled=disabled,
            discovered_asset_refs=discovered_asset_refs,
            display_name=display_name,
            documentation_uri=documentation_uri,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
        )

        asset_body = {
            "extendedLocation": device["extendedLocation"],
            "location": device["location"],
            "properties": properties,
            "tags": tags,
        }

        with console.status(f"Creating asset {asset_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                resource=asset_body
            )
            return wait_for_terminal_state(poller, **kwargs)

    def _handle_asset_show_template(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        template_mode: str,
        asset_config: Optional[str],
    ) -> dict:
        """Return a config/schema template for --show-template and exit early.

        Discovers which asset sub-resource types (datasets, eventGroups, streams) the connector
        supports from its metadata and returns a slimmed template for each supported config.

        OPC UA uses bundled metadata; all other types fetch from OCI via the connector template.
        """
        from .helpers import _slim_schema, _consolidate_warnings
        from .common import EndpointTemplateMode

        if asset_config:
            raise InvalidArgumentValueError(
                "--show-template and --asset-config cannot be used together. "
                "--show-template displays the template and exits without creating an asset."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        endpoint = _get_metadata_endpoint(metadata, connector_type)

        asset_config_template = {}
        all_warnings: List[str] = []
        for section_key, schema_key, config_prop, dest_path, dest_prop in _ASSET_SCHEMA_SECTIONS:
            section = endpoint.get(section_key, {})
            schema = section.get(schema_key)
            if not schema:
                continue
            sub_props = _collect_sub_item_schemas(section)
            if sub_props:
                schema = {
                    **schema,
                    "properties": {**schema.get("properties", {}), **sub_props},
                }
            warnings: List[str] = []
            slimmed = _slim_schema(schema, mode=template_mode, _warnings=warnings)
            all_warnings.extend(warnings)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(slimmed, dict):
                slimmed.pop("$id", None)
            asset_config_template[config_prop] = slimmed

            # Add destination template alongside the config (managementGroups has no destinations)
            if dest_path is not None:
                dest_block = endpoint
                for key in dest_path:
                    if not isinstance(dest_block, dict):
                        dest_block = {}
                        break
                    dest_block = dest_block.get(key, {})
                supported = dest_block.get("supportedDestinations", []) if isinstance(dest_block, dict) else []
                if supported:
                    asset_config_template[dest_prop] = _build_destination_template(
                        supported_destinations=supported,
                        default_destination=dest_block.get("defaultDestination"),
                        mode=template_mode,
                    )

        for w in _consolidate_warnings(all_warnings):
            logger.warning(w)

        return {"connectorType": connector_type, "assetConfig": asset_config_template}

    def create_asset_by_connector_type(
        self,
        instance_name: str,
        instance_resource_group: str,
        connector_type: str,
        asset_name: Optional[str] = None,
        device_name: Optional[str] = None,
        device_endpoint_name: Optional[str] = None,
        asset_config: Optional[str] = None,
        show_template: Optional[str] = None,
        # common asset props
        asset_type_refs: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None,
        description: Optional[str] = None,
        disabled: Optional[bool] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> dict:
        """Generalized create command for a new asset using connector type.

        Supports template discovery (--show-template) and JSON or file-based asset
        configuration (--asset-config) driven by the connector template metadata.
        Fails if the asset already exists.

        OPC UA (Microsoft.OpcUa) uses bundled metadata; all other types fetch from OCI
        via the connector template's connectorMetadataRef.
        """
        # Normalize short keywords (e.g. "opcua" → "Microsoft.OpcUa", "rest" → "Microsoft.Http").
        # Unknown types pass through unchanged (treated as custom/3P).
        connector_type = DeviceEndpointType.get_type_from_keyword(
            connector_type, return_custom_keyword=False
        )

        if show_template:
            return self._handle_asset_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                asset_config=asset_config,
            )

        # Required arg guards
        from azure.cli.core.azclierror import RequiredArgumentMissingError
        if not asset_name:
            raise RequiredArgumentMissingError("--name is required.")
        if not device_name:
            raise RequiredArgumentMissingError("--device is required.")
        if not device_endpoint_name:
            raise RequiredArgumentMissingError("--endpoint is required.")

        # Get device to validate endpoint type and resolve location/extendedLocation
        device, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            device_name=device_name,
            device_endpoint_name=device_endpoint_name,
        )

        # Fail if asset already exists — create does not upsert
        from azure.core.exceptions import ResourceNotFoundError as _AzureNotFoundError
        try:
            self.ops.get(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
            )
            raise InvalidArgumentValueError(
                f"Asset '{asset_name}' already exists. Use 'az iot ops ns asset update' to update it."
            )
        except InvalidArgumentValueError:
            raise
        except _AzureNotFoundError:
            pass

        # Parse and validate asset_config if provided
        additional_config_props = {}
        if asset_config:
            additional_config_props = self._load_and_validate_asset_config(
                asset_config=asset_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )

        properties = {
            "deviceRef": {
                "deviceName": device_name,
                "endpointName": device_endpoint_name,
            }
        }
        properties.update(additional_config_props)

        _update_asset_props(
            properties=properties,
            asset_type_refs=asset_type_refs,
            attributes=attributes,
            description=description,
            disabled=disabled,
            display_name=display_name,
            documentation_uri=documentation_uri,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
        )

        asset_body = {
            "extendedLocation": device["extendedLocation"],
            "location": device["location"],
            "properties": properties,
            "tags": tags,
        }

        with console.status(f"Creating asset {asset_name}..."):
            poller = self.ops.begin_create_or_replace(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                resource=asset_body,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def update_asset_by_connector_type(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_config: Optional[str] = None,
        show_template: Optional[str] = None,
        # common asset props
        asset_type_refs: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None,
        description: Optional[str] = None,
        disabled: Optional[bool] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> dict:
        """Generalized update command for an existing asset.

        Supports template discovery (--show-template) — connector type is derived from
        the existing asset so --connector-type is not needed. Uses PATCH semantics;
        fields not provided are left unchanged.
        """
        # Fetch the existing asset to derive connector type and namespace
        existing_asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )

        # Derive connector type from the device endpoint — ARM does not persist connectorType
        # as a property on the asset resource.  The device's inbound endpoint endpointType is
        # the authoritative source and is always available via the asset's deviceRef.
        device_ref = existing_asset.get("properties", {}).get("deviceRef", {})
        device_name_ref = device_ref.get("deviceName", "")
        endpoint_name_ref = device_ref.get("endpointName", "")
        namespace_from_asset = parse_resource_id(existing_asset["id"])
        device = self.device_ops.get(
            resource_group_name=namespace_from_asset["resource_group"],
            namespace_name=namespace_from_asset["name"],
            device_name=device_name_ref,
        )
        endpoint = (
            device.get("properties", {})
            .get("endpoints", {})
            .get("inbound", {})
            .get(endpoint_name_ref, {})
        )
        connector_type = endpoint.get("endpointType", "")
        if not connector_type:
            raise InvalidArgumentValueError(
                f"Cannot determine connector type for asset '{asset_name}'. "
                f"Device '{device_name_ref}' endpoint '{endpoint_name_ref}' is missing 'endpointType'. "
                "Verify the device endpoint was created correctly."
            )

        if show_template:
            if asset_config:
                raise InvalidArgumentValueError(
                    "--show-template and --asset-config cannot be used together. "
                    "--show-template displays the template and exits without updating the asset."
                )
            from .common import EndpointTemplateMode
            template_mode = show_template.lower()
            if template_mode == EndpointTemplateMode.CONFIG.value:
                # For config mode on update: show the full connector schema structure (same as create)
                # but with existing ARM values pre-filled so the user can see all fields and
                # only edit what they want.
                template_result = self._handle_asset_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    asset_config=None,
                )
                asset_config_tmpl = template_result.get("assetConfig", {})
                existing_props = existing_asset.get("properties", {})
                for _, _, config_prop, _, dest_prop in _ASSET_SCHEMA_SECTIONS:
                    raw = existing_props.get(config_prop)
                    if raw is not None:
                        existing_config = json.loads(raw) if isinstance(raw, str) else raw
                        tmpl_val = asset_config_tmpl.get(config_prop)
                        asset_config_tmpl[config_prop] = (
                            _deep_merge_template(tmpl_val, existing_config)
                            if isinstance(tmpl_val, dict)
                            else existing_config
                        )
                    if dest_prop is not None:
                        existing_dests = existing_props.get(dest_prop, [])
                        if existing_dests:
                            tmpl_dests = asset_config_tmpl.get(dest_prop, [])
                            asset_config_tmpl[dest_prop] = _merge_destinations_template(
                                tmpl_dests, existing_dests
                            )
                return {"connectorType": connector_type, "assetConfig": asset_config_tmpl}
            else:
                # For schema mode, show connector metadata schema structure (same as create)
                return self._handle_asset_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    asset_config=None,
                )

        # namespace_from_asset already contains the resource_group and name derived from the asset
        # ARM id — no need for a separate get_namespace_for_instance HTTP call.
        namespace = namespace_from_asset

        # Parse and validate asset_config if provided
        additional_config_props = {}
        if asset_config:
            additional_config_props = self._load_and_validate_asset_config(
                asset_config=asset_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )

        update_payload = {}
        if tags:
            update_payload["tags"] = tags

        properties = {}
        properties.update(additional_config_props)

        _update_asset_props(
            properties=properties,
            asset_type_refs=asset_type_refs,
            attributes=attributes,
            description=description,
            disabled=disabled,
            display_name=display_name,
            documentation_uri=documentation_uri,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
        )

        if properties:
            update_payload["properties"] = properties

        with console.status(f"Updating asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )

    def _get_connector_type_and_device(self, asset: dict) -> Tuple[str, dict]:
        """Extract the connector type from an asset and return the fetched device.

        Returns the device alongside the connector type so callers can reuse the device
        (e.g. pass it into ``_check_device_props``) instead of re-fetching it.
        """
        device_ref = asset.get("properties", {}).get("deviceRef", {})
        device_name = device_ref.get("deviceName", "")
        endpoint_name = device_ref.get("endpointName", "")
        namespace = parse_resource_id(asset["id"])

        device = self.device_ops.get(
            resource_group_name=namespace["resource_group"],
            namespace_name=namespace["name"],
            device_name=device_name,
        )
        endpoint = (
            device.get("properties", {})
            .get("endpoints", {})
            .get("inbound", {})
            .get(endpoint_name, {})
        )
        connector_type = endpoint.get("endpointType", "")
        if not connector_type:
            raise InvalidArgumentValueError(
                f"Cannot determine connector type for asset '{asset.get('name', '')}'. "
                f"Device '{device_name}' endpoint '{endpoint_name}' is missing 'endpointType'. "
                "Verify the device endpoint was created correctly."
            )
        return connector_type, device

    def _get_connector_metadata(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
    ) -> dict:
        """Load and return connector metadata for the given connector type.

        For OPC UA: uses bundled metadata (with optional live lookup when instance info is available).
        For other types: fetches from OCI via connector template, which must exist in the instance.
        Raises ResourceNotFoundError if a non-OPC UA connector template is not found.
        """
        from .namespace_devices import DeviceEndpointType as _DEType
        from .helpers import load_opcua_metadata_file as _load_opcua_metadata_file

        is_opcua = connector_type.lower() == _DEType.OPCUA.value.lower()
        if is_opcua:
            from azure.core.exceptions import ResourceNotFoundError as _AzureNotFoundError
            from .helpers import get_opcua_info as _get_opcua_info

            metadata = None
            if instance_name and instance_resource_group:
                try:
                    metadata = _get_opcua_info(self.cmd, instance_name, instance_resource_group)
                except _AzureNotFoundError:
                    pass
            if metadata is None:
                metadata = _load_opcua_metadata_file()
            return metadata

        from ..orchestration.resources.connector_templates import ConnectorTemplates
        connector_templates = ConnectorTemplates(cmd=self.cmd)
        template = connector_templates.get_connector_template_for_type(
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            connector_type=connector_type,
        )
        if template is None:
            from azure.cli.core.azclierror import ResourceNotFoundError
            raise ResourceNotFoundError(
                f"No connector template found for connector type '{connector_type}' "
                f"in instance '{instance_name}'.\n"
                f"A connector template is required for connector type '{connector_type}'.\n"
                "Create one with: az iot ops connector template create ..."
            )
        connector_metadata_ref = template.get("properties", {}).get("connectorMetadataRef")
        if not connector_metadata_ref:
            raise ValidationError(
                f"Connector template for '{connector_type}' is missing connectorMetadataRef. "
                "Cannot proceed."
            )
        from ...util.oci_client import get_oci_client
        oci_client = get_oci_client()
        artifact = oci_client.fetch_first_layer(
            image_ref=connector_metadata_ref,
            cmd=self.cmd,
        )
        return json.loads(artifact.content.decode("utf-8"))

    def _handle_dataset_show_template(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        template_mode: str,
        dataset_config: Optional[str],
    ) -> dict:
        """Return a dataset config/schema template for --show-template and exit early.

        Discovers the datasetConfigurationSchema and supported destinations from connector
        metadata and returns a slimmed template. OPC UA uses bundled metadata; all other types
        require a connector template in the instance.
        """
        from .helpers import _slim_schema, _consolidate_warnings
        from .common import EndpointTemplateMode

        if dataset_config:
            raise InvalidArgumentValueError(
                "--show-template and --dataset-config cannot be used together. "
                "--show-template displays the template and exits without modifying the dataset."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type)
        dataset_section = endpoint.get("datasets", {})
        schema = dataset_section.get("datasetConfigurationSchema")

        dataset_config_template: dict = {}
        all_warnings: List[str] = []

        if schema:
            warnings: List[str] = []
            slimmed = _slim_schema(schema, mode=template_mode, _warnings=warnings)
            all_warnings.extend(warnings)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(slimmed, dict):
                slimmed.pop("$id", None)
            dataset_config_template["datasetConfiguration"] = slimmed

        dest_section = dataset_section.get("destinations", {})
        supported = dest_section.get("supportedDestinations", []) if isinstance(dest_section, dict) else []
        if supported:
            dataset_config_template["destinations"] = _build_destination_template(
                supported_destinations=supported,
                default_destination=dest_section.get("defaultDestination"),
                mode=template_mode,
            )

        for w in _consolidate_warnings(all_warnings):
            logger.warning(w)

        return {"connectorType": connector_type, "datasetConfig": dataset_config_template}

    def _load_and_validate_dataset_config(
        self,
        dataset_config: str,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
    ) -> dict:
        """Load dataset config from file/inline JSON, validate against connector schema, and return
        ARM-ready values.

        Input JSON is expected to be the 'datasetConfig' dict (output of --show-template), e.g.:
          {
            "datasetConfiguration": {...},
            "destinations": [...]
          }
        Or the full --show-template output with 'connectorType' and 'datasetConfig' keys,
        which is auto-unwrapped.

        Returns a dict with:
          - "datasetConfiguration": serialized JSON string (if present)
          - "destinations": list of destination dicts (if present)
        """
        from .helpers import strip_nulls as _strip_nulls

        raw = process_additional_configuration(
            additional_configuration=dataset_config,
            config_type="dataset",
        )
        parsed = json.loads(raw)

        if isinstance(parsed, dict) and "datasetConfig" in parsed:
            provided = parsed.get("connectorType")
            if provided and connector_type and provided.lower() != connector_type.lower():
                raise InvalidArgumentValueError(
                    f"Config connectorType '{provided}' does not match asset connectorType '{connector_type}'."
                )
            parsed = parsed["datasetConfig"]

        if not isinstance(parsed, dict) or not {"datasetConfiguration", "destinations"}.intersection(parsed):
            raise InvalidArgumentValueError(
                "--dataset-config must be a JSON object with 'datasetConfiguration' "
                "and/or 'destinations' keys."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type) if metadata else None
        dataset_section = endpoint.get("datasets", {}) if endpoint else {}

        result = {}

        config_data_raw = parsed.get("datasetConfiguration")
        if config_data_raw is not None:
            config_data = _strip_nulls(config_data_raw)
            schema = dataset_section.get("datasetConfigurationSchema") if dataset_section else None
            if schema:
                from ...util.schema_validation import check_json_schema, validate_data_against_schema
                skip_reason = check_json_schema(schema)
                if skip_reason:
                    logger.warning("Skipping datasetConfiguration validation: %s", skip_reason)
                else:
                    validate_data_against_schema(schema, config_data, name="datasetConfiguration")
            result["datasetConfiguration"] = json.dumps(config_data)

        dest_raw = parsed.get("destinations")
        if dest_raw is not None:
            dest_data = _strip_nulls(dest_raw)
            if not isinstance(dest_data, list):
                raise InvalidArgumentValueError(
                    "--dataset-config 'destinations' must be a JSON array of destination objects."
                )
            filtered: List[dict] = []
            for item in dest_data:
                if not isinstance(item, dict):
                    raise InvalidArgumentValueError(
                        "--dataset-config 'destinations' entries must be JSON objects."
                    )
                if not item.get("configuration"):
                    logger.warning(
                        "Ignoring destination '%s' because its configuration is empty.",
                        item.get("target"),
                    )
                    continue
                filtered.append(item)
            dest_data = filtered
            if dest_data:
                dest_section = dataset_section.get("destinations", {}) if dataset_section else {}
                supported = (
                    dest_section.get("supportedDestinations", [])
                    if isinstance(dest_section, dict) else []
                )
                if supported:
                    for dest_item in dest_data:
                        target = dest_item.get("target")
                        if target and target not in supported:
                            raise InvalidArgumentValueError(
                                f"Destination target '{target}' is not supported for datasets. "
                                f"Supported: {supported}."
                            )
                result["destinations"] = dest_data

        return result

    def _handle_datapoint_show_template(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        template_mode: str,
        datapoint_config: Optional[str],
    ) -> dict:
        """Return a datapoint config/schema template for --show-template and exit early."""
        from .helpers import _slim_schema, _consolidate_warnings
        from .common import EndpointTemplateMode

        if datapoint_config:
            raise InvalidArgumentValueError(
                "--show-template and --datapoint-config cannot be used together. "
                "--show-template displays the template and exits without modifying the datapoint."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type)
        dataset_section = endpoint.get("datasets", {})
        dp_section = dataset_section.get("dataPoints", {})
        schema = dp_section.get("dataPointConfigurationSchema")

        datapoint_config_template: dict = {}
        all_warnings: List[str] = []

        if schema:
            warnings: List[str] = []
            slimmed = _slim_schema(schema, mode=template_mode, _warnings=warnings)
            all_warnings.extend(warnings)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(slimmed, dict):
                slimmed.pop("$id", None)
            datapoint_config_template["datapointConfiguration"] = slimmed

        for w in _consolidate_warnings(all_warnings):
            logger.warning(w)

        return {"connectorType": connector_type, "datapointConfig": datapoint_config_template}

    def _load_and_validate_datapoint_config(
        self,
        datapoint_config: str,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
    ) -> dict:
        """Load datapoint config from file/inline JSON, validate against connector schema.

        Input JSON is expected to be the 'datapointConfig' dict (output of --show-template), e.g.:
          {
            "datapointConfiguration": {...}
          }
        Or the full --show-template output with 'connectorType' and 'datapointConfig' keys,
        which is auto-unwrapped.

        Returns a dict with:
          - "datapointConfiguration": serialized JSON string (if present)
        """
        from .helpers import strip_nulls as _strip_nulls

        raw = process_additional_configuration(
            additional_configuration=datapoint_config,
            config_type="datapoint",
        )
        parsed = json.loads(raw)

        if isinstance(parsed, dict) and "datapointConfig" in parsed:
            provided = parsed.get("connectorType")
            if provided and connector_type and provided.lower() != connector_type.lower():
                raise InvalidArgumentValueError(
                    f"Config connectorType '{provided}' does not match asset connectorType '{connector_type}'."
                )
            parsed = parsed["datapointConfig"]

        if not isinstance(parsed, dict) or "datapointConfiguration" not in parsed:
            raise InvalidArgumentValueError(
                "--datapoint-config must be a JSON object with a 'datapointConfiguration' key."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type) if metadata else None
        dataset_section = endpoint.get("datasets", {}) if endpoint else {}
        dp_section = dataset_section.get("dataPoints", {}) if dataset_section else {}

        result = {}

        config_data_raw = parsed.get("datapointConfiguration")
        if config_data_raw is not None:
            config_data = _strip_nulls(config_data_raw)
            schema = dp_section.get("dataPointConfigurationSchema") if dp_section else None
            if schema:
                from ...util.schema_validation import check_json_schema, validate_data_against_schema
                skip_reason = check_json_schema(schema)
                if skip_reason:
                    logger.warning("Skipping datapointConfiguration validation: %s", skip_reason)
                else:
                    validate_data_against_schema(schema, config_data, name="datapointConfiguration")
            result["datapointConfiguration"] = json.dumps(config_data)

        return result

    def add_dataset_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        dataset_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        dataset_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generalized add-dataset that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --dataset-config for
        JSON or file-based connector-specific dataset configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            return self._handle_dataset_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                dataset_config=dataset_config,
            )

        # Cluster connectivity check
        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        datasets = asset["properties"].get("datasets", [])
        unmatched_datasets = [ds for ds in datasets if ds["name"] != dataset_name]
        if len(unmatched_datasets) < len(datasets) and not replace:
            raise InvalidArgumentValueError(
                f"Dataset '{dataset_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing dataset."
            )

        new_dataset: dict = {
            "name": dataset_name,
            "datasetConfiguration": None,
            "destinations": [],
            "dataPoints": [],
            "typeRef": type_ref,
        }
        if data_source:
            new_dataset["dataSource"] = data_source

        if dataset_config:
            config_result = self._load_and_validate_dataset_config(
                dataset_config=dataset_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
            if "datasetConfiguration" in config_result:
                new_dataset["datasetConfiguration"] = config_result["datasetConfiguration"]
            if "destinations" in config_result:
                new_dataset["destinations"] = config_result["destinations"]

        unmatched_datasets.append(new_dataset)
        update_payload = {"properties": {"datasets": unmatched_datasets}}

        with console.status(f"Adding dataset {dataset_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            datasets = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]
            result = next((dset for dset in datasets if dset["name"] == dataset_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Dataset '{dataset_name}' was not found in asset '{asset_name}' after update."
                )
            return result

    def update_dataset_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        dataset_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        dataset_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generalized update-dataset that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --dataset-config for
        JSON or file-based connector-specific dataset configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            from .common import EndpointTemplateMode
            template_mode = show_template.lower()
            if template_mode == EndpointTemplateMode.CONFIG.value:
                # For config mode on update: show the full connector schema structure (same as add)
                # but with existing ARM values pre-filled so the user can see all fields and
                # only edit what they want.
                if dataset_config:
                    raise InvalidArgumentValueError(
                        "--show-template and --dataset-config cannot be used together. "
                        "--show-template displays the template and exits without modifying the dataset."
                    )
                datasets_existing = asset["properties"].get("datasets", [])
                existing = next((d for d in datasets_existing if d["name"] == dataset_name), None)
                if existing is None:
                    raise InvalidArgumentValueError(
                        f"Dataset '{dataset_name}' not found in asset '{asset_name}'."
                    )
                # Get the full schema template (nulls for all fields)
                template_result = self._handle_dataset_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    dataset_config=None,
                )
                dataset_config_tmpl = template_result.get("datasetConfig", {})
                # Pre-fill datasetConfiguration from ARM
                raw_config = existing.get("datasetConfiguration")
                if raw_config:
                    existing_config = json.loads(raw_config) if isinstance(raw_config, str) else raw_config
                    tmpl_dc = dataset_config_tmpl.get("datasetConfiguration")
                    dataset_config_tmpl["datasetConfiguration"] = (
                        _deep_merge_template(tmpl_dc, existing_config)
                        if isinstance(tmpl_dc, dict)
                        else existing_config
                    )
                # Pre-fill destinations from ARM
                existing_dests = existing.get("destinations", [])
                if existing_dests:
                    tmpl_dests = dataset_config_tmpl.get("destinations", [])
                    dataset_config_tmpl["destinations"] = _merge_destinations_template(
                        tmpl_dests, existing_dests
                    )
                return {"connectorType": connector_type, "datasetConfig": dataset_config_tmpl}
            else:
                # For schema mode, show connector metadata schema structure (same as add)
                return self._handle_dataset_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    dataset_config=dataset_config,
                )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        datasets = asset["properties"].get("datasets", [])
        dataset_list = [dset for dset in datasets if dset["name"] == dataset_name]
        if not dataset_list:
            raise InvalidArgumentValueError(
                f"Dataset '{dataset_name}' not found in asset '{asset_name}'."
            )
        dataset = dataset_list[0]

        if dataset_config is not None:
            config_result = self._load_and_validate_dataset_config(
                dataset_config=dataset_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
            if "datasetConfiguration" in config_result:
                dataset["datasetConfiguration"] = config_result["datasetConfiguration"]
            if "destinations" in config_result:
                dataset["destinations"] = config_result["destinations"]

        if data_source is not None:
            dataset["dataSource"] = data_source
        if type_ref is not None:
            dataset["typeRef"] = type_ref

        update_payload = {"properties": {"datasets": datasets}}
        with console.status(f"Updating dataset {dataset_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            datasets = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]
            result = next((dset for dset in datasets if dset["name"] == dataset_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Dataset '{dataset_name}' was not found in asset '{asset_name}' after update."
                )
            return result

    def add_dataset_datapoint_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        dataset_name: str,
        datapoint_name: str,
        data_source: str,
        type_ref: Optional[str] = None,
        replace: bool = False,
        datapoint_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> List[dict]:
        """Generalized add-datapoint that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --datapoint-config for
        JSON or file-based connector-specific datapoint configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            return self._handle_datapoint_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                datapoint_config=datapoint_config,
            )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        dataset = _get_sub_property(asset, dataset_name, property_key="datasets")
        datapoints = dataset["dataPoints"]
        non_matched_points = [point for point in datapoints if point["name"] != datapoint_name]
        if len(non_matched_points) < len(datapoints) and not replace:
            raise InvalidArgumentValueError(
                f"Datapoint '{datapoint_name}' already exists in dataset '{dataset_name}' "
                f"of asset '{asset_name}'. Use --replace to overwrite the existing datapoint."
            )

        datapoint: dict = {"name": datapoint_name, "dataSource": data_source}
        if type_ref:
            datapoint["typeRef"] = type_ref

        if datapoint_config:
            config_result = self._load_and_validate_datapoint_config(
                datapoint_config=datapoint_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
            if "datapointConfiguration" in config_result:
                datapoint["dataPointConfiguration"] = config_result["datapointConfiguration"]

        non_matched_points.append(datapoint)
        dataset["dataPoints"] = non_matched_points

        update_payload = {"properties": {"datasets": asset["properties"]["datasets"]}}
        with console.status(f"Updating asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def _load_and_validate_asset_config(
        self,
        asset_config: str,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
    ) -> dict:
        """Load asset config from a file path or inline JSON and validate each sub-config.

        The input is expected to be the 'assetConfig' dict (output of --show-template), e.g.:
          {
            "defaultDatasetsConfiguration": {...},
            "defaultEventsConfiguration": {...}
          }
        Or the full --show-template output with 'connectorType' and 'assetConfig' keys,
        which is auto-unwrapped.

        Returns a dict of ARM property key → payload-ready value for each config present.
        Configuration properties are returned as serialized JSON strings, while destination
        properties (e.g. defaultDatasetsDestinations) are returned as native Python lists.
        """
        from .helpers import strip_nulls as _strip_nulls

        raw = process_additional_configuration(
            additional_configuration=asset_config,
            config_type="asset",
        )
        parsed = json.loads(raw)

        # Auto-unwrap --show-template output
        if isinstance(parsed, dict) and "assetConfig" in parsed:
            provided = parsed.get("connectorType")
            if provided and connector_type and provided.lower() != connector_type.lower():
                raise InvalidArgumentValueError(
                    f"Config connectorType '{provided}' does not match asset connectorType '{connector_type}'."
                )
            parsed = parsed["assetConfig"]

        _asset_config_keys = {s[2] for s in _ASSET_SCHEMA_SECTIONS} | {s[4] for s in _ASSET_SCHEMA_SECTIONS if s[4]}
        if not isinstance(parsed, dict) or not _asset_config_keys.intersection(parsed):
            raise InvalidArgumentValueError(
                "--asset-config must be a JSON object with defaultDatasetsConfiguration, "
                "defaultEventsConfiguration, and/or defaultStreamsConfiguration keys."
            )

        # Load metadata for schema validation
        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        endpoint = _get_metadata_endpoint(metadata, connector_type) if metadata else None

        result = {}
        for section_key, schema_key, config_prop, dest_path, dest_prop in _ASSET_SCHEMA_SECTIONS:
            # Handle config
            if config_prop in parsed and parsed[config_prop] is not None:
                config_data = _strip_nulls(parsed[config_prop])
                section = (endpoint or {}).get(section_key, {}) if endpoint else {}
                schema = section.get(schema_key) if section else None
                if schema and endpoint:
                    sub_props = _collect_sub_item_schemas(section)
                    if sub_props:
                        schema = {
                            **schema,
                            "properties": {**schema.get("properties", {}), **sub_props},
                        }
                if schema:
                    from ...util.schema_validation import check_json_schema, validate_data_against_schema
                    skip_reason = check_json_schema(schema)
                    if skip_reason:
                        logger.warning("Skipping %s validation: %s", config_prop, skip_reason)
                    else:
                        validate_data_against_schema(schema, config_data, name=config_prop)
                result[config_prop] = json.dumps(config_data)

            # Handle destinations (managementGroups has no destinations)
            if dest_prop is not None and dest_prop in parsed and parsed[dest_prop] is not None:
                dest_data = _strip_nulls(parsed[dest_prop])
                # Filter out destination entries where all configuration fields were null
                # (template placeholders that the user didn't fill in).  An entry with an
                # empty configuration dict would fail ARM's required-field validation.
                if isinstance(dest_data, list):
                    dest_data = [
                        item for item in dest_data
                        if not isinstance(item, dict) or item.get("configuration")
                    ]
                if not dest_data:
                    continue
                # Validate target is in supported list from metadata
                dest_block = endpoint or {}
                for key in (dest_path or []):
                    dest_block = dest_block.get(key, {}) if isinstance(dest_block, dict) else {}
                supported = dest_block.get("supportedDestinations", []) if isinstance(dest_block, dict) else []
                if supported and isinstance(dest_data, list):
                    for dest_item in dest_data:
                        target = dest_item.get("target") if isinstance(dest_item, dict) else None
                        if target and target not in supported:
                            raise InvalidArgumentValueError(
                                f"Destination target '{target}' is not supported for {dest_prop}. "
                                f"Supported: {supported}."
                            )
                result[dest_prop] = dest_data

        return result

    def delete(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        confirm_yes: bool = False,
        **kwargs
    ):
        # should bail prompt
        if not should_continue_prompt(confirm_yes):
            return

        namespace = get_namespace_for_instance(
            cmd=self.cmd,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group
        )

        with console.status(f"Deleting asset {asset_name}..."):
            poller = self.ops.begin_delete(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(
        self,
        asset_name: str,
        resource_group: str,
        namespace_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        check_cluster: bool = False
    ) -> dict:
        if not namespace_name:
            # assume resource group is instance resource group
            namespace = get_namespace_for_instance(
                cmd=self.cmd,
                instance_name=instance_name,
                instance_resource_group=resource_group
            )
            namespace_name = namespace["name"]
            resource_group = namespace["resource_group"]

        asset = self.ops.get(
            resource_group_name=resource_group, namespace_name=namespace_name, asset_name=asset_name
        )
        if check_cluster:
            check_cluster_connectivity(self.cmd, asset)

        return asset

    # note the usage of Azure Resource Graph over the list api
    def query_assets(
        self,
        asset_name: Optional[str] = None,
        instance_name: Optional[str] = None,
        instance_resource_group: Optional[str] = None,
        custom_query: Optional[str] = None,
        device_name: Optional[str] = None,
        device_endpoint_name: Optional[str] = None,
        disabled: Optional[bool] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
    ) -> dict:
        """
        Queries the asset using Azure Resource Graph.
        """
        query = "Resources | where type =~ '{}'".format(NAMESPACE_ASSET_RESOURCE_TYPE)

        # for now, keep it simple
        # ideas for later on, add namespace (needs id parsing), device endpoint type (will need to add joins)
        def _build_query_body(
            **params: dict
        ) -> str:
            param_mapping = {
                "asset_name": "name",
                "device_name": "properties.deviceRef.deviceName",
                "device_endpoint_name": "properties.deviceRef.endpointName",
                "display_name": "properties.displayName",
                "documentation_uri": "properties.documentationUri",
                "external_asset_id": "properties.externalAssetId",
                "hardware_revision": "properties.hardwareRevision",
                "manufacturer": "properties.manufacturer",
                "manufacturer_uri": "properties.manufacturerUri",
                "model": "properties.model",
                "product_code": "properties.productCode",
                "serial_number": "properties.serialNumber",
                "software_revision": "properties.softwareRevision",
            }
            query_body = get_query(
                param_mapping=param_mapping,
                params=params
            )
            return (
                query_body + " | extend customLocation = tostring(extendedLocation.name) "
                "| extend provisioningState = properties.provisioningState "
                "| project id, customLocation, location, name, resourceGroup, provisioningState, "
                "tags, type, subscriptionId"
            )

        query += custom_query or _build_query_body(
            asset_name=asset_name,
            device_name=device_name,
            device_endpoint_name=device_endpoint_name,
            disabled=disabled,
            display_name=display_name,
            documentation_uri=documentation_uri,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
        )

        query = get_instance_query(
            query=query,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            project_away_custom_location=False
        )
        logger.info(f"Querying assets with query: {query}")

        return self.query(query=query)

    def update(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        asset_type_refs: Optional[List[str]] = None,
        attributes: Optional[List[str]] = None,
        description: Optional[str] = None,
        disabled: Optional[bool] = None,
        discovered_asset_refs: Optional[List[str]] = None,
        display_name: Optional[str] = None,
        documentation_uri: Optional[str] = None,
        external_asset_id: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        manufacturer: Optional[str] = None,
        manufacturer_uri: Optional[str] = None,
        model: Optional[str] = None,
        product_code: Optional[str] = None,
        serial_number: Optional[str] = None,
        software_revision: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> dict:
        # need original asset default configurations to update
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        asset_properties = asset["properties"]

        # update payload
        update_payload = {}
        if tags:
            update_payload["tags"] = tags

        properties = {}

        # handle the configs + destinations
        original_configs = {
            "original_dataset_configuration": asset_properties.get("defaultDatasetsConfiguration"),
            "original_event_configuration": asset_properties.get("defaultEventsConfiguration"),
            "original_mgmt_configuration": asset_properties.get("defaultManagementGroupsConfiguration"),
            "original_streams_configuration": asset_properties.get("defaultStreamsConfiguration"),
            "original_dataset_destinations": asset_properties.get("defaultDatasetsDestinations"),
            "original_event_destinations": asset_properties.get("defaultEventsDestinations"),
            "original_stream_destinations": asset_properties.get("defaultStreamsDestinations"),
        }
        config_destinations = _process_configs(
            asset_type=asset_type,
            **original_configs,
            **kwargs
        )
        # might need to do some processing in the future
        properties.update(config_destinations)

        _update_asset_props(
            properties=properties,
            asset_type_refs=asset_type_refs,
            attributes=attributes,
            description=description,
            disabled=disabled,
            discovered_asset_refs=discovered_asset_refs,
            display_name=display_name,
            documentation_uri=documentation_uri,
            external_asset_id=external_asset_id,
            hardware_revision=hardware_revision,
            manufacturer=manufacturer,
            manufacturer_uri=manufacturer_uri,
            model=model,
            product_code=product_code,
            serial_number=serial_number,
            software_revision=software_revision,
        )

        if properties:
            update_payload["properties"] = properties

        with console.status(f"Updating asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )

    # DATASETS - only allowed for opcua and custom assets
    def add_dataset(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        dataset_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        # TODO: future pr, import datapoints from file
        **kwargs
    ):
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # get the datasets from the asset
        datasets = asset["properties"].get("datasets", [])
        # remove dataset if it exists
        unmatched_datasets = [ds for ds in datasets if ds["name"] != dataset_name]
        if len(unmatched_datasets) < len(datasets) and not replace:
            raise InvalidArgumentValueError(
                f"Dataset '{dataset_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing dataset."
            )

        # create the dataset
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            **kwargs
        )
        new_dataset = {
            "name": dataset_name,
            "datasetConfiguration": processed_configs.get("datasetsConfiguration"),
            "destinations": processed_configs.get("datasetsDestinations", []),
            "dataPoints": [],  # TODO: future pr, add datapoints
            "typeRef": type_ref
        }
        if data_source:
            new_dataset["dataSource"] = data_source

        self._validate_imported_items(
            items=[new_dataset],
            validate_fn=lambda v, d: v.validate_dataset(d),
            resource_label=f"Dataset '{dataset_name}'",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        unmatched_datasets.append(new_dataset)

        update_payload = {
            "properties": {
                "datasets": unmatched_datasets
            }
        }
        with console.status(f"Adding dataset {dataset_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            datasets = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]
            result = next((dset for dset in datasets if dset["name"] == dataset_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Dataset '{dataset_name}' was not found in asset '{asset_name}' after update."
                )
            return result

    def list_datasets(self, asset_name: str, instance_name: str, instance_resource_group: str) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return asset["properties"].get("datasets", [])

    def show_dataset(
        self, asset_name: str, instance_name: str, instance_resource_group: str, dataset_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return _get_sub_property(asset, dataset_name, property_key="datasets")

    def update_dataset(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        dataset_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        **kwargs
    ):
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # get the datasets from the asset
        datasets = asset["properties"].get("datasets", [])
        # check if dataset exists
        dataset = [dset for dset in datasets if dset["name"] == dataset_name]
        if not dataset:
            raise InvalidArgumentValueError(
                f"Dataset '{dataset_name}' not found in asset '{asset_name}'. "
            )
        dataset = dataset[0]

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_dataset_configuration=dataset.get("datasetConfiguration"),
            **kwargs
        )

        # update the dataset properties
        if "datasetsConfiguration" in processed_configs:
            dataset["datasetConfiguration"] = processed_configs["datasetsConfiguration"]
        if data_source:
            dataset["dataSource"] = data_source
        if type_ref:
            dataset["typeRef"] = type_ref
        if "datasetsDestinations" in processed_configs:
            dataset["destinations"] = processed_configs["datasetsDestinations"]

        self._validate_imported_items(
            items=[dataset],
            validate_fn=lambda v, d: v.validate_dataset(d),
            resource_label=f"Updated dataset '{dataset_name}'",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        update_payload = {
            "properties": {
                "datasets": datasets
            }
        }
        with console.status(f"Updating dataset {dataset_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            datasets = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]
            result = next((dset for dset in datasets if dset["name"] == dataset_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Dataset '{dataset_name}' was not found in asset '{asset_name}' after update."
                )
            return result

    def remove_dataset(
        self, asset_name: str, instance_name: str, instance_resource_group: str, dataset_name: str, **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        datasets = asset["properties"].get("datasets", [])
        # note that delete should be ok with dataset not there
        remaining_datasets = [dset for dset in datasets if dset["name"] != dataset_name]

        if len(remaining_datasets) == len(datasets):
            logger.info(f"Dataset '{dataset_name}' not found in asset '{asset_name}'.")
            return datasets  # no change, return the original datasets

        update_payload = {
            "properties": {
                "datasets": remaining_datasets
            }
        }
        with console.status(f"Removing dataset {dataset_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]

    def export_datasets(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export all datasets from an asset to a file (JSON or YAML)."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        datasets = asset["properties"].get("datasets", [])

        file_path = dump_content_to_file(
            content=datasets,
            file_name=f"{asset_name}_datasets",
            extension=extension,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "dataset_count": len(datasets)}

    def import_datasets(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import datasets from file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        original_datasets = asset["properties"].get("datasets", [])

        imported_datasets = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_datasets,
            point_key="name",
            replace=replace
        )

        self._validate_imported_items(
            items=imported_datasets,
            validate_fn=lambda v, d: v.validate_dataset(d),
            resource_label="Datasets",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        update_payload = {
            "properties": {
                "datasets": imported_datasets
            }
        }

        with console.status(f"Importing datasets for asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["datasets"]

    def add_dataset_datapoint(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        dataset_name: str,
        datapoint_name: str,
        data_source: str,
        # Custom
        custom_configuration: Optional[str] = None,
        # OPCUA specific
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        # note that for now, we will not expose typeref for dataset datapoints
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        dataset = _get_sub_property(asset, dataset_name, property_key="datasets")

        # get the datapoints
        datapoints = dataset["dataPoints"]
        non_matched_points = [point for point in datapoints if point["name"] != datapoint_name]
        if len(non_matched_points) < len(datapoints) and not replace:
            raise InvalidArgumentValueError(
                f"Datapoint '{datapoint_name}' already exists in dataset '{dataset_name}' of asset '{asset_name}'. "
                "Use --replace to overwrite the existing datapoint."
            )

        # create the datapoint
        datapoint = _create_datapoint(
            datapoint_name=datapoint_name,
            data_source=data_source,
            queue_size=queue_size,
            sampling_interval=sampling_interval,
            custom_configuration=custom_configuration,
            type_ref=type_ref
        )

        self._validate_imported_items(
            items=[datapoint],
            validate_fn=lambda v, dp: v.validate_datapoint(dp),
            resource_label=f"Datapoint '{datapoint_name}'",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        non_matched_points.append(datapoint)
        dataset["dataPoints"] = non_matched_points

        update_payload = {
            "properties": {
                "datasets": asset["properties"]["datasets"]
            }
        }

        with console.status(f"Updating asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def list_dataset_datapoints(
        self, asset_name: str, instance_name: str, instance_resource_group: str, dataset_name: str
    ) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def remove_dataset_datapoint(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        dataset_name: str,
        datapoint_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        dataset = _get_sub_property(asset, dataset_name, property_key="datasets")
        datapoints = dataset.get("dataPoints", [])
        # note that delete should be ok with datapoint not there
        dataset["dataPoints"] = [dp for dp in datapoints if dp["name"] != datapoint_name]

        if len(dataset["dataPoints"]) == len(datapoints):
            logger.info(
                f"Datapoint '{datapoint_name}' not found in dataset '{dataset_name}' of asset '{asset_name}'."
            )
            return dataset["dataPoints"]

        update_payload = {
            "properties": {
                "datasets": asset["properties"]["datasets"]
            }
        }
        with console.status(
            f"Removing datapoint {datapoint_name} from dataset {dataset_name} in asset {asset_name}..."
        ):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def export_dataset_datapoints(
        self,
        asset_name: str,
        dataset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export datapoints from a dataset to a file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        dataset = _get_sub_property(asset, dataset_name, property_key="datasets")
        datapoints = dataset.get("dataPoints", [])

        # Convert to CSV format if requested
        fieldnames = None
        if extension == FileType.csv.value:
            default_configuration = dataset.get("datasetConfiguration", "{}")
            if default_configuration == "{}":
                default_configuration = asset["properties"].get("defaultDatasetsConfiguration", "{}")
            fieldnames = _convert_sub_points_to_csv_namespace(
                sub_points=datapoints,
                sub_point_type="dataPoints",
                default_configuration=default_configuration,
                portal_friendly=True
            )

        file_path = dump_content_to_file(
            content=datapoints,
            file_name=f"{asset_name}_{dataset_name}_datapoints",
            extension=extension,
            fieldnames=fieldnames,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "datapoint_count": len(datapoints)}

    def import_dataset_datapoints(
        self,
        asset_name: str,
        dataset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import datapoints from file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        # Find the target dataset
        datasets = asset["properties"].get("datasets", [])
        dataset = None
        for dset in datasets:
            if dset["name"] == dataset_name:
                dataset = dset
                break

        if dataset is None:
            raise InvalidArgumentValueError(
                f"Dataset '{dataset_name}' not found in asset '{asset_name}'. "
                f"Create the dataset first before importing datapoints."
            )

        # Merge or replace datapoints based on flag
        original_datapoints = dataset.get("dataPoints", [])
        imported_datapoints = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_datapoints,
            point_key="name",
            replace=replace,
            csv_converter=_convert_sub_points_from_csv_namespace
        )

        self._validate_imported_items(
            items=imported_datapoints,
            validate_fn=lambda v, dp: v.validate_datapoint(dp),
            resource_label="Datapoints",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        dataset["dataPoints"] = imported_datapoints

        update_payload = {
            "properties": {
                "datasets": datasets
            }
        }

        with console.status(f"Importing datapoints for dataset {dataset_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, dataset_name, property_key="datasets")["dataPoints"]

    def export_event_groups(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export event-groups from an asset to a file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        event_groups = asset["properties"].get("eventGroups", [])

        file_path = dump_content_to_file(
            content=event_groups,
            file_name=f"{asset_name}_event_groups",
            extension=extension,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "event_group_count": len(event_groups)}

    def import_event_groups(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import event-groups from file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        original_event_groups = asset["properties"].get("eventGroups", [])
        imported_event_groups = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_event_groups,
            point_key="name",
            replace=replace
        )

        self._validate_imported_items(
            items=imported_event_groups,
            validate_fn=lambda v, eg: v.validate_event_group(eg),
            resource_label="Event-groups",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        update_payload = {
            "properties": {
                "eventGroups": imported_event_groups
            }
        }

        with console.status(f"Importing event-groups for asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return asset["properties"].get("eventGroups", [])

    def export_event_group_events(
        self,
        asset_name: str,
        event_group_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export events from an event-group to a file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        event_group = _get_sub_property(asset, event_group_name, property_key="eventGroups")
        events = event_group.get("events", [])

        # Convert to CSV format if requested
        fieldnames = None
        if extension == FileType.csv.value:
            default_configuration = event_group.get("eventGroupConfiguration", "{}")
            if default_configuration == "{}":
                default_configuration = asset["properties"].get("defaultEventsConfiguration", "{}")
            fieldnames = _convert_sub_points_to_csv_namespace(
                sub_points=events,
                sub_point_type="events",
                default_configuration=default_configuration,
                portal_friendly=True
            )

        file_path = dump_content_to_file(
            content=events,
            file_name=f"{asset_name}_{event_group_name}_events",
            extension=extension,
            fieldnames=fieldnames,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "event_count": len(events)}

    def import_event_group_events(
        self,
        asset_name: str,
        event_group_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import events from file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        event_groups = asset["properties"].get("eventGroups", [])
        event_group = None
        for eg in event_groups:
            if eg["name"] == event_group_name:
                event_group = eg
                break

        if event_group is None:
            raise InvalidArgumentValueError(
                f"Event-group '{event_group_name}' not found in asset '{asset_name}'. "
                f"Create the event-group first before importing events."
            )

        original_events = event_group.get("events", [])

        # Get default destinations from event-group or asset configuration
        default_destinations = event_group.get("defaultDestinations")
        if not default_destinations:
            default_destinations = asset["properties"].get("defaultEventsDestinations", [])

        imported_events = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_events,
            point_key="name",
            replace=replace,
            csv_converter=_convert_sub_points_from_csv_namespace
        )

        self._validate_imported_items(
            items=imported_events,
            validate_fn=lambda v, e: v.validate_event(e),
            resource_label="Events",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        # Always auto-assign destinations if not present (required by API)
        for event in imported_events:
            if "destinations" not in event or not event["destinations"]:
                event["destinations"] = deepcopy(default_destinations)

        event_group["events"] = imported_events

        update_payload = {
            "properties": {
                "eventGroups": event_groups
            }
        }

        with console.status(f"Importing events for event-group {event_group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, event_group_name, property_key="eventGroups")["events"]

    def _handle_event_group_show_template(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        template_mode: str,
        event_group_config: Optional[str],
    ) -> dict:
        """Return an event-group config/schema template for --show-template and exit early.

        Discovers the eventGroupConfigurationSchema and supported destinations from connector
        metadata and returns a slimmed template. OPC UA uses bundled metadata; all other types
        require a connector template in the instance.
        """
        from .helpers import _slim_schema, _consolidate_warnings
        from .common import EndpointTemplateMode

        if event_group_config:
            raise InvalidArgumentValueError(
                "--show-template and --event-group-config cannot be used together. "
                "--show-template displays the template and exits without modifying the event-group."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type)
        eg_section = endpoint.get("eventGroups", {})
        schema = eg_section.get("eventGroupConfigurationSchema")

        event_group_config_template: dict = {}
        all_warnings: List[str] = []

        if schema:
            warnings: List[str] = []
            slimmed = _slim_schema(schema, mode=template_mode, _warnings=warnings)
            all_warnings.extend(warnings)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(slimmed, dict):
                slimmed.pop("$id", None)
            event_group_config_template["eventGroupConfiguration"] = slimmed

        # Destinations metadata lives at the event level; the event-group's defaultDestinations
        # share the same supported destination set.
        destinations = self._build_event_destinations_template(eg_section, template_mode)
        if destinations is not None:
            event_group_config_template["destinations"] = destinations

        for w in _consolidate_warnings(all_warnings):
            logger.warning(w)

        return {"connectorType": connector_type, "eventGroupConfig": event_group_config_template}

    def _build_event_destinations_template(self, eg_section: dict, template_mode: str) -> Optional[list]:
        """Build a destinations template from the connector's supported event destinations.

        Event-group defaultDestinations and event destinations share the same supported set, which
        lives at ``eventGroups.events.destinations``. Returns None when no destinations are supported.
        """
        events_section = eg_section.get("events", {}) if isinstance(eg_section, dict) else {}
        dest_section = events_section.get("destinations", {}) if isinstance(events_section, dict) else {}
        supported = dest_section.get("supportedDestinations", []) if isinstance(dest_section, dict) else []
        if not supported:
            return None
        return _build_destination_template(
            supported_destinations=supported,
            default_destination=dest_section.get("defaultDestination"),
            mode=template_mode,
        )

    def _load_and_validate_event_group_config(
        self,
        event_group_config: str,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
    ) -> dict:
        """Load event-group config from file/inline JSON, validate against connector schema, and
        return ARM-ready values.

        Input JSON is expected to be the 'eventGroupConfig' dict (output of --show-template), e.g.:
          {
            "eventGroupConfiguration": {...},
            "destinations": [...]
          }
        Or the full --show-template output with 'connectorType' and 'eventGroupConfig' keys,
        which is auto-unwrapped.

        Returns a dict with:
          - "eventGroupConfiguration": serialized JSON string (if present)
          - "destinations": list of destination dicts (if present)
        """
        from .helpers import strip_nulls as _strip_nulls

        raw = process_additional_configuration(
            additional_configuration=event_group_config,
            config_type="event-group",
        )
        parsed = json.loads(raw)

        if isinstance(parsed, dict) and "eventGroupConfig" in parsed:
            provided = parsed.get("connectorType")
            if provided and connector_type and provided.lower() != connector_type.lower():
                raise InvalidArgumentValueError(
                    f"Config connectorType '{provided}' does not match asset connectorType '{connector_type}'."
                )
            parsed = parsed["eventGroupConfig"]

        if not isinstance(parsed, dict) or not {"eventGroupConfiguration", "destinations"}.intersection(parsed):
            raise InvalidArgumentValueError(
                "--event-group-config must be a JSON object with 'eventGroupConfiguration' "
                "and/or 'destinations' keys."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type) if metadata else None
        eg_section = endpoint.get("eventGroups", {}) if endpoint else {}

        result = {}

        config_data_raw = parsed.get("eventGroupConfiguration")
        if config_data_raw is not None:
            config_data = _strip_nulls(config_data_raw)
            schema = eg_section.get("eventGroupConfigurationSchema") if eg_section else None
            if schema:
                from ...util.schema_validation import check_json_schema, validate_data_against_schema
                skip_reason = check_json_schema(schema)
                if skip_reason:
                    logger.warning("Skipping eventGroupConfiguration validation: %s", skip_reason)
                else:
                    validate_data_against_schema(schema, config_data, name="eventGroupConfiguration")
            result["eventGroupConfiguration"] = json.dumps(config_data)

        dest_raw = parsed.get("destinations")
        if dest_raw is not None:
            dest_data = self._validate_event_destinations(dest_raw, eg_section)
            if dest_data:
                result["destinations"] = dest_data

        return result

    def _filter_and_validate_destinations(
        self, dest_raw, supported: List[str], resource_label: str
    ) -> List[dict]:
        """Filter a destinations list (dropping entries with empty configuration) and validate the
        remaining targets against the connector's supported destination set.

        Shared by the event, event-group, and stream config loaders. ``supported`` is the already
        resolved ``supportedDestinations`` list; ``resource_label`` is used in error messages.
        """
        from .helpers import strip_nulls as _strip_nulls

        dest_data = _strip_nulls(dest_raw)
        if not isinstance(dest_data, list):
            raise InvalidArgumentValueError(
                "'destinations' must be a JSON array of destination objects."
            )
        filtered: List[dict] = []
        for item in dest_data:
            if not isinstance(item, dict):
                raise InvalidArgumentValueError(
                    "'destinations' entries must be JSON objects."
                )
            if not item.get("configuration"):
                logger.warning(
                    "Ignoring destination '%s' because its configuration is empty.",
                    item.get("target"),
                )
                continue
            filtered.append(item)
        if filtered and supported:
            for dest_item in filtered:
                target = dest_item.get("target")
                if target and target not in supported:
                    raise InvalidArgumentValueError(
                        f"Destination target '{target}' is not supported for {resource_label}. "
                        f"Supported: {supported}."
                    )
        return filtered

    def _validate_event_destinations(self, dest_raw, eg_section: dict) -> List[dict]:
        """Validate and filter a destinations list against the connector's supported event
        destinations. Shared by event-group and event config loaders."""
        events_section = eg_section.get("events", {}) if eg_section else {}
        dest_section = events_section.get("destinations", {}) if isinstance(events_section, dict) else {}
        supported = (
            dest_section.get("supportedDestinations", [])
            if isinstance(dest_section, dict) else []
        )
        return self._filter_and_validate_destinations(dest_raw, supported, "events")

    def _handle_event_show_template(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        template_mode: str,
        event_config: Optional[str],
    ) -> dict:
        """Return an event config/schema template for --show-template and exit early."""
        from .helpers import _slim_schema, _consolidate_warnings
        from .common import EndpointTemplateMode

        if event_config:
            raise InvalidArgumentValueError(
                "--show-template and --event-config cannot be used together. "
                "--show-template displays the template and exits without modifying the event."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type)
        eg_section = endpoint.get("eventGroups", {})
        events_section = eg_section.get("events", {})
        schema = events_section.get("eventConfigurationSchema")

        event_config_template: dict = {}
        all_warnings: List[str] = []

        if schema:
            warnings: List[str] = []
            slimmed = _slim_schema(schema, mode=template_mode, _warnings=warnings)
            all_warnings.extend(warnings)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(slimmed, dict):
                slimmed.pop("$id", None)
            event_config_template["eventConfiguration"] = slimmed

        destinations = self._build_event_destinations_template(eg_section, template_mode)
        if destinations is not None:
            event_config_template["destinations"] = destinations

        for w in _consolidate_warnings(all_warnings):
            logger.warning(w)

        return {"connectorType": connector_type, "eventConfig": event_config_template}

    def _load_and_validate_event_config(
        self,
        event_config: str,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
    ) -> dict:
        """Load event config from file/inline JSON, validate against connector schema.

        Input JSON is expected to be the 'eventConfig' dict (output of --show-template), e.g.:
          {
            "eventConfiguration": {...},
            "destinations": [...]
          }
        Or the full --show-template output with 'connectorType' and 'eventConfig' keys,
        which is auto-unwrapped.

        Returns a dict with:
          - "eventConfiguration": serialized JSON string (if present)
          - "destinations": list of destination dicts (if present)
        """
        from .helpers import strip_nulls as _strip_nulls

        raw = process_additional_configuration(
            additional_configuration=event_config,
            config_type="event",
        )
        parsed = json.loads(raw)

        if isinstance(parsed, dict) and "eventConfig" in parsed:
            provided = parsed.get("connectorType")
            if provided and connector_type and provided.lower() != connector_type.lower():
                raise InvalidArgumentValueError(
                    f"Config connectorType '{provided}' does not match asset connectorType '{connector_type}'."
                )
            parsed = parsed["eventConfig"]

        if not isinstance(parsed, dict) or not {"eventConfiguration", "destinations"}.intersection(parsed):
            raise InvalidArgumentValueError(
                "--event-config must be a JSON object with 'eventConfiguration' "
                "and/or 'destinations' keys."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type) if metadata else None
        eg_section = endpoint.get("eventGroups", {}) if endpoint else {}
        events_section = eg_section.get("events", {}) if eg_section else {}

        result = {}

        config_data_raw = parsed.get("eventConfiguration")
        if config_data_raw is not None:
            config_data = _strip_nulls(config_data_raw)
            schema = events_section.get("eventConfigurationSchema") if events_section else None
            if schema:
                from ...util.schema_validation import check_json_schema, validate_data_against_schema
                skip_reason = check_json_schema(schema)
                if skip_reason:
                    logger.warning("Skipping eventConfiguration validation: %s", skip_reason)
                else:
                    validate_data_against_schema(schema, config_data, name="eventConfiguration")
            result["eventConfiguration"] = json.dumps(config_data)

        dest_raw = parsed.get("destinations")
        if dest_raw is not None:
            dest_data = self._validate_event_destinations(dest_raw, eg_section)
            if dest_data:
                result["destinations"] = dest_data

        return result

    def add_event_group_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        event_group_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generalized add-event-group that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --event-group-config for
        JSON or file-based connector-specific event-group configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            return self._handle_event_group_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                event_group_config=event_group_config,
            )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        original_egs = asset["properties"].get("eventGroups", [])
        new_egs = [event for event in original_egs if event["name"] != group_name]
        if len(new_egs) < len(original_egs) and not replace:
            raise InvalidArgumentValueError(
                f"Event group '{group_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing event group."
            )

        new_eg: dict = {
            "name": group_name,
            "eventGroupConfiguration": None,
            "defaultDestinations": [],
            "events": [],
            "typeRef": type_ref,
        }
        if data_source:
            new_eg["dataSource"] = data_source

        if event_group_config:
            config_result = self._load_and_validate_event_group_config(
                event_group_config=event_group_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
            if "eventGroupConfiguration" in config_result:
                new_eg["eventGroupConfiguration"] = config_result["eventGroupConfiguration"]
            if "destinations" in config_result:
                new_eg["defaultDestinations"] = config_result["destinations"]

        new_egs.append(new_eg)
        update_payload = {"properties": {"eventGroups": new_egs}}

        with console.status(f"Adding event group {group_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="eventGroups")

    def update_event_group_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        event_group_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generalized update-event-group that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --event-group-config for
        JSON or file-based connector-specific event-group configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            from .common import EndpointTemplateMode
            template_mode = show_template.lower()
            if template_mode == EndpointTemplateMode.CONFIG.value:
                if event_group_config:
                    raise InvalidArgumentValueError(
                        "--show-template and --event-group-config cannot be used together. "
                        "--show-template displays the template and exits without modifying the event-group."
                    )
                egs_existing = asset["properties"].get("eventGroups", [])
                existing = next((d for d in egs_existing if d["name"] == group_name), None)
                if existing is None:
                    raise InvalidArgumentValueError(
                        f"Event group '{group_name}' not found in asset '{asset_name}'."
                    )
                template_result = self._handle_event_group_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    event_group_config=None,
                )
                eg_config_tmpl = template_result.get("eventGroupConfig", {})
                raw_config = existing.get("eventGroupConfiguration")
                if raw_config:
                    existing_config = json.loads(raw_config) if isinstance(raw_config, str) else raw_config
                    tmpl_ec = eg_config_tmpl.get("eventGroupConfiguration")
                    eg_config_tmpl["eventGroupConfiguration"] = (
                        _deep_merge_template(tmpl_ec, existing_config)
                        if isinstance(tmpl_ec, dict)
                        else existing_config
                    )
                existing_dests = existing.get("defaultDestinations", [])
                if existing_dests:
                    tmpl_dests = eg_config_tmpl.get("destinations", [])
                    eg_config_tmpl["destinations"] = _merge_destinations_template(
                        tmpl_dests, existing_dests
                    )
                return {"connectorType": connector_type, "eventGroupConfig": eg_config_tmpl}
            else:
                return self._handle_event_group_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    event_group_config=event_group_config,
                )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        event_groups = asset["properties"].get("eventGroups", [])
        group_list = [eg for eg in event_groups if eg["name"] == group_name]
        if not group_list:
            raise InvalidArgumentValueError(
                f"Event group '{group_name}' not found in asset '{asset_name}'."
            )
        group = group_list[0]

        if event_group_config is not None:
            config_result = self._load_and_validate_event_group_config(
                event_group_config=event_group_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
            if "eventGroupConfiguration" in config_result:
                group["eventGroupConfiguration"] = config_result["eventGroupConfiguration"]
            if "destinations" in config_result:
                group["defaultDestinations"] = config_result["destinations"]

        if data_source is not None:
            group["dataSource"] = data_source
        if type_ref is not None:
            group["typeRef"] = type_ref

        update_payload = {"properties": {"eventGroups": event_groups}}
        with console.status(f"Updating event group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="eventGroups")

    def add_event_group_event_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        event_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        event_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> List[dict]:
        """Generalized add-event that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --event-config for
        JSON or file-based connector-specific event configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            return self._handle_event_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                event_config=event_config,
            )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        event_group = _get_sub_property(asset, group_name, property_key="eventGroups")
        og_events = event_group.get("events", [])
        remaining_events = [ev for ev in og_events if ev["name"] != event_name]
        if len(remaining_events) < len(og_events) and not replace:
            raise InvalidArgumentValueError(
                f"event '{event_name}' already exists in event group '{group_name}' of asset '{asset_name}'. "
                "Use --replace to overwrite the existing event."
            )

        event: dict = {"name": event_name}
        if data_source:
            event["dataSource"] = data_source
        if type_ref:
            event["typeRef"] = type_ref

        if event_config:
            config_result = self._load_and_validate_event_config(
                event_config=event_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
            if "eventConfiguration" in config_result:
                event["eventConfiguration"] = config_result["eventConfiguration"]
            if "destinations" in config_result:
                event["destinations"] = config_result["destinations"]

        remaining_events.append(event)
        event_group["events"] = remaining_events

        update_payload = {"properties": {"eventGroups": asset["properties"]["eventGroups"]}}
        with console.status(f"Adding event {event_name} to event group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="eventGroups")["events"]

    # EVENT GROUPS - allowed for opcua, onvif, and custom assets
    def add_event_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        # TODO: future pr, add events
        **kwargs
    ) -> dict:
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        original_egs = asset["properties"].get("eventGroups", [])
        # remove event group if it exists
        new_egs = [event for event in original_egs if event["name"] != group_name]
        if len(new_egs) < len(original_egs) and not replace:
            raise InvalidArgumentValueError(
                f"Event group '{group_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing event group."
            )

        # create the event group
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            **kwargs
        )
        new_eg = {
            "name": group_name,
            "eventGroupConfiguration": processed_configs.get("eventsConfiguration"),
            "defaultDestinations": processed_configs.get("eventsDestinations", []),
            "events": [],
            "typeRef": type_ref
        }
        if data_source:
            new_eg["dataSource"] = data_source
        new_egs.append(new_eg)

        update_payload = {
            "properties": {
                "eventGroups": new_egs
            }
        }
        with console.status(f"Adding event group {group_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="eventGroups")

    def list_event_groups(self, asset_name: str, instance_name: str, instance_resource_group: str) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return asset["properties"].get("eventGroups", [])

    def show_event_group(
        self, asset_name: str, instance_name: str, instance_resource_group: str, group_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return _get_sub_property(asset, group_name, property_key="eventGroups")

    def remove_event_group(
        self, asset_name: str, instance_name: str, instance_resource_group: str, group_name: str, **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        current_egs = asset["properties"].get("eventGroups", [])
        # note that delete should be ok with event not there
        remaining_egs = [event for event in current_egs if event["name"] != group_name]

        # if the event is not found, we should not update
        if len(remaining_egs) == len(current_egs):
            logger.info(f"Event group '{group_name}' not found in asset '{asset_name}'.")
            return current_egs

        update_payload = {
            "properties": {
                "eventGroups": remaining_egs
            }
        }
        with console.status(f"Removing event group {group_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            # TODO: should remove event return the list of events or just nothing?
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["eventGroups"]

    def update_event_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        data_source: Optional[str] = None,
        type_ref: Optional[str] = None,
        **kwargs
    ):
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # check if event exists
        group = _get_sub_property(asset, group_name, property_key="eventGroups")

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_event_configuration=group.get("eventConfiguration"),
            **kwargs
        )

        # update the event properties
        if "eventsConfiguration" in processed_configs:
            group["eventGroupConfiguration"] = processed_configs["eventsConfiguration"]
        if "eventsDestinations" in processed_configs:
            group["defaultDestinations"] = processed_configs["eventsDestinations"]
        if data_source:
            group["dataSource"] = data_source
        if type_ref:
            group["typeRef"] = type_ref

        # get the events from the asset (note the event should be updated here already)
        groups = asset["properties"].get("eventGroups", [])
        update_payload = {
            "properties": {
                "eventGroups": groups
            }
        }
        with console.status(f"Updating event {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="eventGroups")

    # EVENT GROUP EVENTS - allowed for opcua, onvif, and custom assets
    def add_event_group_event(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        event_name: str,
        data_source: Optional[str] = None,
        # Custom
        custom_configuration: Optional[str] = None,
        # OPCUA specific
        queue_size: Optional[int] = None,
        sampling_interval: Optional[int] = None,
        condition_refresh: Optional[bool] = None,
        event_destinations: Optional[List[dict]] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
    ) -> dict:
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )

        # check if event exists
        event_group = _get_sub_property(asset, group_name, property_key="eventGroups")

        # get the events
        og_events = event_group.get("events", [])
        remaining_events = [ev for ev in og_events if ev["name"] != event_name]
        if len(remaining_events) < len(og_events) and not replace:
            raise InvalidArgumentValueError(
                f"event '{event_name}' already exists in event group '{group_name}' of asset '{asset_name}'. "
                "Use --replace to overwrite the existing event."
            )

        # create the event
        event = _create_event(
            event_name=event_name,
            data_source=data_source,
            type_ref=type_ref,
            custom_configuration=custom_configuration,
            event_destinations=event_destinations,
            queue_size=queue_size,
            sampling_interval=sampling_interval,
            condition_refresh=condition_refresh,
        )
        remaining_events.append(event)
        event_group["events"] = remaining_events

        # get the events from the asset
        event_groups = asset["properties"].get("eventGroups", [])
        update_payload = {
            "properties": {
                "eventGroups": event_groups
            }
        }
        with console.status(f"Adding event {event_name} to event group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            # note that we return a list of events
            return _get_sub_property(asset, group_name, property_key="eventGroups")["events"]

    def list_event_group_events(
        self, asset_name: str, instance_name: str, instance_resource_group: str, group_name: str
    ):
        event = self.show_event_group(
            asset_name=asset_name,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
            group_name=group_name
        )
        return event.get("events", [])

    def remove_event_group_event(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        event_name: str,
        **kwargs
    ):
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        # since we do not check device props (not adding events), we parse namespace this way
        namespace = parse_resource_id(asset["id"])
        event_group = _get_sub_property(asset, group_name, property_key="eventGroups")
        og_events = event_group.get("events", [])
        # note that delete should be ok with event not there
        event_group["events"] = [ev for ev in og_events if ev["name"] != event_name]

        # no need for update if the event is not found
        if len(event_group["events"]) == len(og_events):
            logger.info(
                f"Event '{event_name}' not found in event group '{group_name}' of asset '{asset_name}'."
            )
            return event_group["events"]

        event_groups = asset["properties"].get("eventGroups", [])
        update_payload = {
            "properties": {
                "eventGroups": event_groups
            }
        }
        with console.status(
            f"Removing event {event_name} from event group {group_name} in asset {asset_name}..."
        ):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            # note that we return a list of events
            return _get_sub_property(asset, group_name, property_key="eventGroups")["events"]

    def _handle_stream_show_template(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        template_mode: str,
        stream_config: Optional[str],
    ) -> dict:
        """Return a stream config/schema template for --show-template and exit early.

        Discovers the streamConfigurationSchema and supported destinations from connector
        metadata and returns a slimmed template. OPC UA uses bundled metadata; all other types
        require a connector template in the instance.
        """
        from .helpers import _slim_schema, _consolidate_warnings
        from .common import EndpointTemplateMode

        if stream_config:
            raise InvalidArgumentValueError(
                "--show-template and --stream-config cannot be used together. "
                "--show-template displays the template and exits without modifying the stream."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type)
        stream_section = endpoint.get("streams", {})
        schema = stream_section.get("streamConfigurationSchema")

        stream_config_template: dict = {}
        all_warnings: List[str] = []

        if schema:
            warnings: List[str] = []
            slimmed = _slim_schema(schema, mode=template_mode, _warnings=warnings)
            all_warnings.extend(warnings)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(slimmed, dict):
                slimmed.pop("$id", None)
            stream_config_template["streamConfiguration"] = slimmed

        destinations = self._build_stream_destinations_template(stream_section, template_mode)
        if destinations is not None:
            stream_config_template["destinations"] = destinations

        for w in _consolidate_warnings(all_warnings):
            logger.warning(w)

        return {"connectorType": connector_type, "streamConfig": stream_config_template}

    def _build_stream_destinations_template(self, stream_section: dict, template_mode: str) -> Optional[list]:
        """Build a destinations template from the connector's supported stream destinations.

        Stream destinations live at ``streams.destinations``. Returns None when no destinations
        are supported.
        """
        dest_section = stream_section.get("destinations", {}) if isinstance(stream_section, dict) else {}
        supported = dest_section.get("supportedDestinations", []) if isinstance(dest_section, dict) else []
        if not supported:
            return None
        return _build_destination_template(
            supported_destinations=supported,
            default_destination=dest_section.get("defaultDestination"),
            mode=template_mode,
        )

    def _validate_stream_destinations(self, dest_raw, stream_section: dict) -> List[dict]:
        """Validate and filter a destinations list against the connector's supported stream
        destinations."""
        dest_section = stream_section.get("destinations", {}) if isinstance(stream_section, dict) else {}
        supported = (
            dest_section.get("supportedDestinations", [])
            if isinstance(dest_section, dict) else []
        )
        return self._filter_and_validate_destinations(dest_raw, supported, "streams")

    def _load_and_validate_stream_config(
        self,
        stream_config: str,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
    ) -> dict:
        """Load stream config from file/inline JSON, validate against connector schema, and
        return ARM-ready values.

        Input JSON is expected to be the 'streamConfig' dict (output of --show-template), e.g.:
          {
            "streamConfiguration": {...},
            "destinations": [...]
          }
        Or the full --show-template output with 'connectorType' and 'streamConfig' keys,
        which is auto-unwrapped.

        Returns a dict with:
          - "streamConfiguration": serialized JSON string (if present)
          - "destinations": list of destination dicts (if present)
        """
        from .helpers import strip_nulls as _strip_nulls

        raw = process_additional_configuration(
            additional_configuration=stream_config,
            config_type="stream",
        )
        parsed = json.loads(raw)

        if isinstance(parsed, dict) and "streamConfig" in parsed:
            provided = parsed.get("connectorType")
            if provided and connector_type and provided.lower() != connector_type.lower():
                raise InvalidArgumentValueError(
                    f"Config connectorType '{provided}' does not match asset connectorType '{connector_type}'."
                )
            parsed = parsed["streamConfig"]

        if not isinstance(parsed, dict) or not {"streamConfiguration", "destinations"}.intersection(parsed):
            raise InvalidArgumentValueError(
                "--stream-config must be a JSON object with 'streamConfiguration' "
                "and/or 'destinations' keys."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type) if metadata else None
        stream_section = endpoint.get("streams", {}) if endpoint else {}

        result = {}

        config_data_raw = parsed.get("streamConfiguration")
        if config_data_raw is not None:
            config_data = _strip_nulls(config_data_raw)
            schema = stream_section.get("streamConfigurationSchema") if stream_section else None
            if schema:
                from ...util.schema_validation import check_json_schema, validate_data_against_schema
                skip_reason = check_json_schema(schema)
                if skip_reason:
                    logger.warning("Skipping streamConfiguration validation: %s", skip_reason)
                else:
                    validate_data_against_schema(schema, config_data, name="streamConfiguration")
            result["streamConfiguration"] = json.dumps(config_data)

        dest_raw = parsed.get("destinations")
        if dest_raw is not None:
            dest_data = self._validate_stream_destinations(dest_raw, stream_section)
            # Preserve an explicitly empty list so callers can clear destinations.
            if dest_data or dest_raw == []:
                result["destinations"] = dest_data

        return result

    def add_stream_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        stream_name: str,
        type_ref: Optional[str] = None,
        replace: bool = False,
        stream_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generalized add-stream that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --stream-config for
        JSON or file-based connector-specific stream configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            return self._handle_stream_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                stream_config=stream_config,
            )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        original_streams = asset["properties"].get("streams", [])
        new_streams = [stream for stream in original_streams if stream["name"] != stream_name]
        if len(new_streams) < len(original_streams) and not replace:
            raise InvalidArgumentValueError(
                f"Stream '{stream_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing stream."
            )

        new_stream: dict = {
            "name": stream_name,
            "streamConfiguration": None,
            "destinations": [],
            "typeRef": type_ref,
        }

        if stream_config:
            config_result = self._load_and_validate_stream_config(
                stream_config=stream_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
            if "streamConfiguration" in config_result:
                new_stream["streamConfiguration"] = config_result["streamConfiguration"]
            if "destinations" in config_result:
                new_stream["destinations"] = config_result["destinations"]

        new_streams.append(new_stream)
        update_payload = {"properties": {"streams": new_streams}}

        with console.status(f"Adding stream {stream_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, stream_name, property_key="streams")

    def update_stream_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        stream_name: str,
        type_ref: Optional[str] = None,
        stream_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generalized update-stream that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --stream-config for
        JSON or file-based connector-specific stream configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            from .common import EndpointTemplateMode
            template_mode = show_template.lower()
            if template_mode == EndpointTemplateMode.CONFIG.value:
                if stream_config:
                    raise InvalidArgumentValueError(
                        "--show-template and --stream-config cannot be used together. "
                        "--show-template displays the template and exits without modifying the stream."
                    )
                streams_existing = asset["properties"].get("streams", [])
                existing = next((s for s in streams_existing if s["name"] == stream_name), None)
                if existing is None:
                    raise InvalidArgumentValueError(
                        f"Stream '{stream_name}' not found in asset '{asset_name}'."
                    )
                template_result = self._handle_stream_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    stream_config=None,
                )
                stream_config_tmpl = template_result.get("streamConfig", {})
                raw_config = existing.get("streamConfiguration")
                if raw_config:
                    existing_config = json.loads(raw_config) if isinstance(raw_config, str) else raw_config
                    tmpl_sc = stream_config_tmpl.get("streamConfiguration")
                    stream_config_tmpl["streamConfiguration"] = (
                        _deep_merge_template(tmpl_sc, existing_config)
                        if isinstance(tmpl_sc, dict)
                        else existing_config
                    )
                existing_dests = existing.get("destinations", [])
                if existing_dests:
                    tmpl_dests = stream_config_tmpl.get("destinations", [])
                    stream_config_tmpl["destinations"] = _merge_destinations_template(
                        tmpl_dests, existing_dests
                    )
                return {"connectorType": connector_type, "streamConfig": stream_config_tmpl}
            else:
                return self._handle_stream_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    stream_config=stream_config,
                )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        streams = asset["properties"].get("streams", [])
        stream_list = [s for s in streams if s["name"] == stream_name]
        if not stream_list:
            raise InvalidArgumentValueError(
                f"Stream '{stream_name}' not found in asset '{asset_name}'."
            )
        stream = stream_list[0]

        if stream_config is not None:
            config_result = self._load_and_validate_stream_config(
                stream_config=stream_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
            )
            if "streamConfiguration" in config_result:
                stream["streamConfiguration"] = config_result["streamConfiguration"]
            if "destinations" in config_result:
                stream["destinations"] = config_result["destinations"]

        if type_ref is not None:
            stream["typeRef"] = type_ref

        update_payload = {"properties": {"streams": streams}}
        with console.status(f"Updating stream {stream_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, stream_name, property_key="streams")

    # STREAMS - allowed for media and custom assets
    def add_stream(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        stream_name: str,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
    ) -> dict:
        # ignoring typeref
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        streams = asset["properties"].get("streams", [])
        # remove stream if it exists
        unmatched_streams = [stream for stream in streams if stream["name"] != stream_name]
        if len(unmatched_streams) < len(streams) and not replace:
            raise InvalidArgumentValueError(
                f"Stream '{stream_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing stream."
            )

        # create the stream
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            **kwargs
        )
        unmatched_streams.append(
            {
                "name": stream_name,
                "streamConfiguration": processed_configs.get("streamsConfiguration"),
                "destinations": processed_configs.get("streamsDestinations", []),
                "typeRef": type_ref
            }
        )

        update_payload = {
            "properties": {
                "streams": unmatched_streams
            }
        }
        with console.status(f"Adding stream {stream_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            streams = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["streams"]
            result = next((stream for stream in streams if stream["name"] == stream_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Stream '{stream_name}' was not found in asset '{asset_name}' after update."
                )
            return result

    def list_streams(self, asset_name: str, instance_name: str, instance_resource_group: str) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return asset["properties"].get("streams", [])

    def show_stream(
        self, asset_name: str, instance_name: str, instance_resource_group: str, stream_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        streams = asset["properties"].get("streams", [])
        stream = next((s for s in streams if s["name"] == stream_name), None)
        if not stream:
            raise InvalidArgumentValueError(f"Stream '{stream_name}' not found in asset '{asset_name}'.")
        return stream

    def remove_stream(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        stream_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        streams = asset["properties"].get("streams", [])
        # note that delete should be ok with stream not there
        remaining_streams = [stream for stream in streams if stream["name"] != stream_name]

        if len(remaining_streams) == len(streams):
            logger.info(f"Stream '{stream_name}' not found in asset '{asset_name}'.")
            return streams

        update_payload = {
            "properties": {
                "streams": remaining_streams
            }
        }
        with console.status(f"Removing stream {stream_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["streams"]

    def update_stream(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        stream_name: str,
        type_ref: Optional[str] = None,
        **kwargs
    ) -> dict:
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # check if stream exists
        streams = asset["properties"].get("streams", [])
        stream = next((s for s in streams if s["name"] == stream_name), None)
        if not stream:
            raise InvalidArgumentValueError(f"Stream '{stream_name}' not found in asset '{asset_name}'.")

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_stream_configuration=stream.get("streamConfiguration"),
            **kwargs
        )

        # update the stream properties
        if "streamsConfiguration" in processed_configs:
            stream["streamConfiguration"] = processed_configs["streamsConfiguration"]
        if "streamsDestinations" in processed_configs:
            stream["destinations"] = processed_configs["streamsDestinations"]
        if type_ref:
            stream["typeRef"] = type_ref

        update_payload = {
            "properties": {
                "streams": streams
            }
        }
        with console.status(f"Updating stream {stream_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            streams = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["streams"]
            result = next((stream for stream in streams if stream["name"] == stream_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Stream '{stream_name}' was not found in asset '{asset_name}' after update."
                )
            return result

    def export_streams(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export streams from an asset to a file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        streams = asset["properties"].get("streams", [])

        # Strip properties that should not be exported (per DOE design)
        export_streams = []
        for stream in streams:
            export_stream = {"name": stream.get("name")}
            # Include streamConfiguration if present (but not destinations - auto-assigned on import)
            if stream.get("streamConfiguration"):
                export_stream["streamConfiguration"] = stream["streamConfiguration"]
            if stream.get("typeRef"):
                export_stream["typeRef"] = stream["typeRef"]
            export_streams.append(export_stream)

        file_path = dump_content_to_file(
            content=export_streams,
            file_name=f"{asset_name}_streams",
            extension=extension,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "stream_count": len(export_streams)}

    def import_streams(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import streams from file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        original_streams = asset["properties"].get("streams", [])

        # Get default destinations from asset configuration (if configured)
        default_destinations = asset["properties"].get("defaultStreamsDestinations") or []

        imported_streams = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_streams,
            point_key="name",
            replace=replace
        )

        self._validate_imported_items(
            items=imported_streams,
            validate_fn=lambda v, s: v.validate_stream(s),
            resource_label="Streams",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        # Always auto-assign destinations if not present (required by API)
        for stream in imported_streams:
            if default_destinations and ("destinations" not in stream or not stream["destinations"]):
                stream["destinations"] = deepcopy(default_destinations)

        update_payload = {
            "properties": {
                "streams": imported_streams
            }
        }

        with console.status(f"Importing streams for asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return asset["properties"].get("streams", [])

    # GENERALIZED MANAGEMENT GROUP / ACTION HELPERS AND METHODS
    def _handle_management_show_template(
        self,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        template_mode: str,
        config: Optional[str],
        *,
        is_action: bool,
    ) -> dict:
        """Return a management group/action config or schema template for --show-template and exit early.

        Discovers the relevant *ConfigurationSchema from connector metadata and returns a slimmed
        template. Management groups and actions have no destinations in the metadata schema. OPC UA
        uses bundled metadata; all other types require a connector template in the instance.
        """
        from .helpers import _slim_schema, _consolidate_warnings
        from .common import EndpointTemplateMode

        config_arg = "--action-config" if is_action else "--mgmt-group-config"
        label = "action" if is_action else "management group"
        config_key = "actionConfiguration" if is_action else "managementGroupConfiguration"
        result_key = "actionConfig" if is_action else "mgmtGroupConfig"

        if config:
            raise InvalidArgumentValueError(
                f"--show-template and {config_arg} cannot be used together. "
                f"--show-template displays the template and exits without modifying the {label}."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type)
        mg_section = endpoint.get("managementGroups", {})
        if is_action:
            schema = mg_section.get("managementGroupActions", {}).get("actionConfigurationSchema")
        else:
            schema = mg_section.get("managementGroupConfigurationSchema")

        config_template: dict = {}
        all_warnings: List[str] = []

        if schema:
            warnings: List[str] = []
            slimmed = _slim_schema(schema, mode=template_mode, _warnings=warnings)
            all_warnings.extend(warnings)
            if template_mode == EndpointTemplateMode.SCHEMA.value and isinstance(slimmed, dict):
                slimmed.pop("$id", None)
            config_template[config_key] = slimmed

        for w in _consolidate_warnings(all_warnings):
            logger.warning(w)

        return {"connectorType": connector_type, result_key: config_template}

    def _load_and_validate_management_config(
        self,
        config: str,
        connector_type: str,
        instance_name: str,
        instance_resource_group: str,
        *,
        is_action: bool,
    ) -> dict:
        """Load management group/action config from file/inline JSON, validate against the connector
        schema, and return ARM-ready values.

        Input JSON is expected to be the 'mgmtGroupConfig'/'actionConfig' dict (output of
        --show-template), e.g. ``{"managementGroupConfiguration": {...}}``, or the full
        --show-template output with 'connectorType' and the config wrapper key, which is
        auto-unwrapped.

        Returns a dict with the serialized configuration JSON string (if present).
        """
        from .helpers import strip_nulls as _strip_nulls

        config_arg = "--action-config" if is_action else "--mgmt-group-config"
        config_type = "action" if is_action else "management group"
        config_key = "actionConfiguration" if is_action else "managementGroupConfiguration"
        result_key = "actionConfig" if is_action else "mgmtGroupConfig"

        raw = process_additional_configuration(
            additional_configuration=config,
            config_type=config_type,
        )
        parsed = json.loads(raw)

        if isinstance(parsed, dict) and result_key in parsed:
            provided = parsed.get("connectorType")
            if provided and connector_type and provided.lower() != connector_type.lower():
                raise InvalidArgumentValueError(
                    f"Config connectorType '{provided}' does not match asset connectorType '{connector_type}'."
                )
            parsed = parsed[result_key]

        if not isinstance(parsed, dict) or config_key not in parsed:
            raise InvalidArgumentValueError(
                f"{config_arg} must be a JSON object with a '{config_key}' key."
            )

        metadata = self._get_connector_metadata(
            connector_type=connector_type,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )
        endpoint = _get_metadata_endpoint(metadata, connector_type) if metadata else None
        mg_section = endpoint.get("managementGroups", {}) if endpoint else {}
        if is_action:
            schema_owner = mg_section.get("managementGroupActions", {}) if mg_section else {}
            schema_key = "actionConfigurationSchema"
        else:
            schema_owner = mg_section
            schema_key = "managementGroupConfigurationSchema"

        result = {}

        config_data_raw = parsed.get(config_key)
        if config_data_raw is not None:
            config_data = _strip_nulls(config_data_raw)
            schema = schema_owner.get(schema_key) if schema_owner else None
            if schema:
                from ...util.schema_validation import check_json_schema, validate_data_against_schema
                skip_reason = check_json_schema(schema)
                if skip_reason:
                    logger.warning("Skipping %s validation: %s", config_key, skip_reason)
                else:
                    validate_data_against_schema(schema, config_data, name=config_key)
            result[config_key] = json.dumps(config_data)

        return result

    def add_management_group_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        data_source: Optional[str] = None,
        default_topic: Optional[str] = None,
        default_timeout: Optional[int] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        mgmt_group_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generalized add-management-group that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --mgmt-group-config for
        JSON or file-based connector-specific management-group configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            return self._handle_management_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                config=mgmt_group_config,
                is_action=False,
            )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        og_mgmt_groups = asset["properties"].get("managementGroups", [])
        remaining_mgmt_groups = [mgmt for mgmt in og_mgmt_groups if mgmt["name"] != group_name]
        if len(remaining_mgmt_groups) < len(og_mgmt_groups) and not replace:
            raise InvalidArgumentValueError(
                f"Management group '{group_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing management group."
            )

        new_mgmt_group: dict = {
            "name": group_name,
            "defaultTopic": default_topic,
            "defaultTimeoutInSeconds": default_timeout,
            "managementGroupConfiguration": None,
            "typeRef": type_ref,
            "actions": [],
        }
        if data_source:
            new_mgmt_group["dataSource"] = data_source

        if mgmt_group_config:
            config_result = self._load_and_validate_management_config(
                config=mgmt_group_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                is_action=False,
            )
            if "managementGroupConfiguration" in config_result:
                new_mgmt_group["managementGroupConfiguration"] = config_result["managementGroupConfiguration"]

        remaining_mgmt_groups.append(new_mgmt_group)
        update_payload = {"properties": {"managementGroups": remaining_mgmt_groups}}

        with console.status(f"Adding management group {group_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="managementGroups")

    def update_management_group_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        data_source: Optional[str] = None,
        default_topic: Optional[str] = None,
        default_timeout: Optional[int] = None,
        type_ref: Optional[str] = None,
        mgmt_group_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> dict:
        """Generalized update-management-group that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --mgmt-group-config for
        JSON or file-based connector-specific management-group configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            from .common import EndpointTemplateMode
            template_mode = show_template.lower()
            if template_mode == EndpointTemplateMode.CONFIG.value:
                if mgmt_group_config:
                    raise InvalidArgumentValueError(
                        "--show-template and --mgmt-group-config cannot be used together. "
                        "--show-template displays the template and exits without modifying the management group."
                    )
                mgs_existing = asset["properties"].get("managementGroups", [])
                existing = next((d for d in mgs_existing if d["name"] == group_name), None)
                if existing is None:
                    raise InvalidArgumentValueError(
                        f"Management group '{group_name}' not found in asset '{asset_name}'."
                    )
                template_result = self._handle_management_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    config=None,
                    is_action=False,
                )
                mg_config_tmpl = template_result.get("mgmtGroupConfig", {})
                raw_config = existing.get("managementGroupConfiguration")
                if raw_config:
                    existing_config = json.loads(raw_config) if isinstance(raw_config, str) else raw_config
                    tmpl_c = mg_config_tmpl.get("managementGroupConfiguration")
                    mg_config_tmpl["managementGroupConfiguration"] = (
                        _deep_merge_template(tmpl_c, existing_config)
                        if isinstance(tmpl_c, dict)
                        else existing_config
                    )
                return {"connectorType": connector_type, "mgmtGroupConfig": mg_config_tmpl}
            else:
                return self._handle_management_show_template(
                    connector_type=connector_type,
                    instance_name=instance_name,
                    instance_resource_group=instance_resource_group,
                    template_mode=template_mode,
                    config=mgmt_group_config,
                    is_action=False,
                )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        mgmt_groups = asset["properties"].get("managementGroups", [])
        group_list = [mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name]
        if not group_list:
            raise InvalidArgumentValueError(
                f"Management group '{group_name}' not found in asset '{asset_name}'."
            )
        group = group_list[0]

        if mgmt_group_config is not None:
            config_result = self._load_and_validate_management_config(
                config=mgmt_group_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                is_action=False,
            )
            if "managementGroupConfiguration" in config_result:
                group["managementGroupConfiguration"] = config_result["managementGroupConfiguration"]

        if default_topic == "":
            group.pop("defaultTopic", None)
        elif default_topic:
            group["defaultTopic"] = default_topic
        if default_timeout is not None:
            group["defaultTimeoutInSeconds"] = default_timeout
        if data_source:
            group["dataSource"] = data_source
        if type_ref:
            group["typeRef"] = type_ref

        update_payload = {"properties": {"managementGroups": mgmt_groups}}
        with console.status(f"Updating management group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="managementGroups")

    def add_management_group_action_generalized(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        action_name: str,
        target_uri: Optional[str] = None,
        topic: Optional[str] = None,
        action_type: Optional[str] = None,
        timeout: Optional[int] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        action_config: Optional[str] = None,
        show_template: Optional[str] = None,
        **kwargs,
    ) -> List[dict]:
        """Generalized add-management-action that detects connector type from the asset.

        Supports --show-template for config/schema discovery and --action-config for
        JSON or file-based connector-specific action configuration. For non-OPC UA
        connectors, a connector template must exist in the instance.
        """
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
        )
        connector_type, device = self._get_connector_type_and_device(asset)

        if show_template:
            return self._handle_management_show_template(
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                template_mode=show_template.lower(),
                config=action_config,
                is_action=True,
            )

        _, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=connector_type,
            asset_name=asset_name,
            asset=asset,
            device=device,
        )

        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")
        actions = mgmt_group.get("actions", [])
        unmatched_actions = [action for action in actions if action["name"] != action_name]
        if len(unmatched_actions) < len(actions) and not replace:
            raise InvalidArgumentValueError(
                f"Action '{action_name}' already exists in management group '{group_name}' "
                f"of asset '{asset_name}'. Use --replace to overwrite the existing action."
            )

        action: dict = {
            "name": action_name,
            "targetUri": target_uri,
            "topic": topic,
            "actionType": action_type,
            "timeoutInSeconds": timeout,
            "typeRef": type_ref,
        }

        if action_config:
            config_result = self._load_and_validate_management_config(
                config=action_config,
                connector_type=connector_type,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group,
                is_action=True,
            )
            if "actionConfiguration" in config_result:
                action["actionConfiguration"] = config_result["actionConfiguration"]

        unmatched_actions.append(action)
        mgmt_group["actions"] = unmatched_actions

        update_payload = {"properties": {"managementGroups": asset["properties"]["managementGroups"]}}
        with console.status(f"Adding action {action_name} to management group {group_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload,
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="managementGroups")["actions"]

    # Management Groups - allowed for opcua, onvif, and custom assets
    def add_management_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        data_source: Optional[str] = None,
        default_topic: Optional[str] = None,
        default_timeout: Optional[int] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
        # TODO: add in mgmt configurations
    ) -> dict:
        # ignoring typeref
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        og_mgmt_groups = asset["properties"].get("managementGroups", [])
        # remove management group if it exists
        remaining_mgmt_groups = [mgmt for mgmt in og_mgmt_groups if mgmt["name"] != group_name]
        if len(remaining_mgmt_groups) < len(og_mgmt_groups) and not replace:
            raise InvalidArgumentValueError(
                f"Management group '{group_name}' already exists in asset '{asset_name}'. "
                "Use --replace to overwrite the existing management group."
            )

        # create the management group
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            **kwargs
        )
        new_mgmt_group = {
            "name": group_name,
            "defaultTopic": default_topic,
            "defaultTimeoutInSeconds": default_timeout,
            "managementGroupConfiguration": processed_configs.get("managementGroupsConfiguration"),
            "typeRef": type_ref,
            "actions": []  # TODO: future, add actions in add_management_group
        }
        if data_source:
            new_mgmt_group["dataSource"] = data_source
        remaining_mgmt_groups.append(new_mgmt_group)
        update_payload = {
            "properties": {
                "managementGroups": remaining_mgmt_groups
            }
        }
        with console.status(f"Adding management group {group_name} to asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            mgmt_groups = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]
            result = next((mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Management group '{group_name}' was not found in asset '{asset_name}' after update."
                )
            return result

    def list_management_groups(
        self, asset_name: str, instance_name: str, instance_resource_group: str
    ) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return asset["properties"].get("managementGroups", [])

    def show_management_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        return _get_sub_property(asset, group_name, property_key="managementGroups")

    def remove_management_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        mgmt_groups = asset["properties"].get("managementGroups", [])
        # note that delete should be ok with management group not there
        remaining_mgmt_groups = [mgmt for mgmt in mgmt_groups if mgmt["name"] != group_name]

        if len(remaining_mgmt_groups) == len(mgmt_groups):
            logger.info(f"Management group '{group_name}' not found in asset '{asset_name}'.")
            return mgmt_groups

        update_payload = {
            "properties": {
                "managementGroups": remaining_mgmt_groups
            }
        }
        with console.status(f"Removing management group {group_name} from asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            return self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]

    def update_management_group(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        data_source: Optional[str] = None,
        default_topic: Optional[str] = None,
        default_timeout: Optional[int] = None,
        type_ref: Optional[str] = None,
        **kwargs
    ) -> dict:
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        # check if management group exists
        mgmt_groups = asset["properties"].get("managementGroups", [])
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")

        # process the configs + destinations
        processed_configs = _process_configs(
            asset_type=asset_type,
            default=False,
            original_management_group_configuration=mgmt_group.get("managementGroupConfiguration"),
            **kwargs
        )

        # update the management group properties
        if "managementGroupsConfiguration" in processed_configs:
            mgmt_group["managementGroupConfiguration"] = processed_configs["managementGroupsConfiguration"]
        if default_topic == "":
            mgmt_group.pop("defaultTopic", None)
        elif default_topic:
            mgmt_group["defaultTopic"] = default_topic
        if default_timeout is not None:
            mgmt_group["defaultTimeoutInSeconds"] = default_timeout
        if data_source:
            mgmt_group["dataSource"] = data_source
        if type_ref:
            mgmt_group["typeRef"] = type_ref

        update_payload = {
            "properties": {
                "managementGroups": mgmt_groups
            }
        }
        with console.status(f"Updating management group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            mgmt_groups = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]
            result = next((mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Management group '{group_name}' was not found in asset '{asset_name}' after update."
                )
            return result

    # MANAGEMENT GROUP ACTIONS
    def add_management_group_action(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        asset_type: str,
        group_name: str,
        action_name: str,
        target_uri: str,
        topic: Optional[str] = None,
        action_type: Optional[str] = None,
        timeout: Optional[int] = None,
        custom_configuration: Optional[str] = None,
        type_ref: Optional[str] = None,
        replace: bool = False,
        **kwargs
    ) -> dict:
        # also ignore typeref here
        asset, namespace = self._check_device_props(
            instance_resource_group=instance_resource_group,
            instance_name=instance_name,
            asset_type=asset_type,
            asset_name=asset_name
        )
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")

        actions = mgmt_group.get("actions", [])
        unmatched_actions = [action for action in actions if action["name"] != action_name]
        if len(unmatched_actions) < len(actions) and not replace:
            raise InvalidArgumentValueError(
                f"Action '{action_name}' already exists in management group '{group_name}' "
                f"of asset '{asset_name}'. Use --replace to overwrite the existing action."
            )

        # create the action
        action = {
            "name": action_name,
            "targetUri": target_uri,
            "topic": topic,
            "actionType": action_type,
            "timeoutInSeconds": timeout,
            "typeRef": type_ref
        }
        if custom_configuration:
            action["actionConfiguration"] = process_additional_configuration(
                custom_configuration, config_type="action"

            )
        unmatched_actions.append(action)
        mgmt_group["actions"] = unmatched_actions

        update_payload = {
            "properties": {
                "managementGroups": asset["properties"]["managementGroups"]
            }
        }
        with console.status(f"Adding action {action_name} to management group {group_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            mgmt_groups = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]
            result = next((mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Management group '{group_name}' was not found in asset '{asset_name}' after update."
                )
            return result["actions"]

    def list_management_group_actions(
        self, asset_name: str, instance_name: str, instance_resource_group: str, group_name: str
    ) -> List[dict]:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")
        return mgmt_group.get("actions", [])

    def remove_management_group_action(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        action_name: str,
        **kwargs
    ) -> dict:
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")

        actions = mgmt_group.get("actions", [])
        # note that delete should be ok with action not there
        remaining_actions = [action for action in actions if action["name"] != action_name]

        if len(remaining_actions) == len(actions):
            logger.info(
                f"Action '{action_name}' not found in management group '{group_name}' "
                f"of asset '{asset_name}'."
            )
            return actions

        mgmt_group["actions"] = remaining_actions

        update_payload = {
            "properties": {
                "managementGroups": asset["properties"]["managementGroups"]
            }
        }
        with console.status(f"Removing action {action_name} from management group {group_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            mgmt_groups = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )["properties"]["managementGroups"]
            result = next((mgmt for mgmt in mgmt_groups if mgmt["name"] == group_name), None)
            if result is None:
                raise CLIInternalError(
                    f"Management group '{group_name}' was not found in asset '{asset_name}' after update."
                )
            return result["actions"]

    def export_management_groups(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export management groups from an asset to a file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        mgmt_groups = asset["properties"].get("managementGroups", [])

        # Strip properties that should not be exported (per DOE design)
        export_mgmt_groups = []
        for mgmt_group in mgmt_groups:
            export_group = {
                "name": mgmt_group.get("name"),
            }
            # Include optional fields if present
            if mgmt_group.get("dataSource"):
                export_group["dataSource"] = mgmt_group["dataSource"]
            if mgmt_group.get("defaultTopic"):
                export_group["defaultTopic"] = mgmt_group["defaultTopic"]
            if mgmt_group.get("defaultTimeoutInSeconds") is not None:
                export_group["defaultTimeoutInSeconds"] = mgmt_group["defaultTimeoutInSeconds"]
            if mgmt_group.get("typeRef"):
                export_group["typeRef"] = mgmt_group["typeRef"]
            # Note: 'actions' array is NOT exported (exported separately)
            # Note: 'key' and 'managementGroupConfiguration' are stripped
            export_mgmt_groups.append(export_group)

        file_path = dump_content_to_file(
            content=export_mgmt_groups,
            file_name=f"{asset_name}_management_groups",
            extension=extension,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "management_group_count": len(export_mgmt_groups)}

    def import_management_groups(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import management groups from file. Supports JSON and YAML formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])
        original_mgmt_groups = asset["properties"].get("managementGroups", [])

        imported_mgmt_groups = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_mgmt_groups,
            point_key="name",
            replace=replace
        )

        self._validate_imported_items(
            items=imported_mgmt_groups,
            validate_fn=lambda v, mg: v.validate_management_group(mg),
            resource_label="Management groups",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        # Always preserve existing actions if merging
        for mgmt_group in imported_mgmt_groups:
            if "actions" not in mgmt_group:
                name = mgmt_group.get("name", "")
                original = next((g for g in original_mgmt_groups if g["name"] == name), None)
                mgmt_group["actions"] = original.get("actions", []) if original else []

        update_payload = {
            "properties": {
                "managementGroups": imported_mgmt_groups
            }
        }

        with console.status(f"Importing management groups for asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return asset["properties"].get("managementGroups", [])

    def export_management_group_actions(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        extension: str = FileType.json.value,
        output_dir: str = ".",
        replace: bool = False
    ) -> dict:
        """Export actions from a management group to a file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group
        )
        mgmt_group = _get_sub_property(asset, group_name, property_key="managementGroups")
        actions = mgmt_group.get("actions", [])

        # Strip properties that should not be exported (per DOE design)
        export_actions = []
        for action in actions:
            export_action = {
                "name": action.get("name"),
                "targetUri": action.get("targetUri"),
            }
            # Include optional fields if present
            if action.get("actionType"):
                export_action["actionType"] = action["actionType"]
            if action.get("topic"):
                export_action["topic"] = action["topic"]
            if action.get("timeoutInSeconds") is not None:
                export_action["timeoutInSeconds"] = action["timeoutInSeconds"]
            if action.get("typeRef"):
                export_action["typeRef"] = action["typeRef"]
            # Note: 'key' and 'managementGroup' are stripped
            export_actions.append(export_action)

        # Convert to CSV format if requested
        fieldnames = None
        if extension == FileType.csv.value:
            fieldnames = _convert_actions_to_csv(export_actions)

        file_path = dump_content_to_file(
            content=export_actions,
            file_name=f"{asset_name}_{group_name}_actions",
            extension=extension,
            fieldnames=fieldnames,
            output_dir=output_dir,
            replace=replace
        )
        return {"file_path": file_path, "action_count": len(export_actions)}

    def import_management_group_actions(
        self,
        asset_name: str,
        instance_name: str,
        instance_resource_group: str,
        group_name: str,
        file_path: str,
        replace: bool = False,
        **kwargs
    ) -> List[dict]:
        """Import actions from file. Supports JSON, YAML, and CSV formats."""
        asset = self.show(
            asset_name=asset_name,
            instance_name=instance_name,
            resource_group=instance_resource_group,
            check_cluster=True
        )
        namespace = parse_resource_id(asset["id"])

        # Check that management group exists
        mgmt_groups = asset["properties"].get("managementGroups", [])
        if not mgmt_groups:
            raise InvalidArgumentValueError(
                f"No management groups found in asset '{asset_name}'. "
                "Create a management group first before importing actions."
            )

        mgmt_group = None
        for mg in mgmt_groups:
            if mg["name"] == group_name:
                mgmt_group = mg
                break

        if mgmt_group is None:
            raise InvalidArgumentValueError(
                f"Management group '{group_name}' not found in asset '{asset_name}'. "
                f"Create the management group first before importing actions."
            )

        original_actions = mgmt_group.get("actions", [])
        imported_actions = _process_namespace_sub_points_file_path(
            file_path=file_path,
            original_items=original_actions,
            point_key="name",
            replace=replace,
            csv_converter=_convert_actions_from_csv
        )

        self._validate_imported_items(
            items=imported_actions,
            validate_fn=lambda v, a: v.validate_action(a),
            resource_label="Actions",
            asset=asset,
            instance_name=instance_name,
            instance_resource_group=instance_resource_group,
        )

        # Always default actionType to 'Call' if not specified
        for action in imported_actions:
            if not action.get("actionType"):
                action["actionType"] = "Call"

        mgmt_group["actions"] = imported_actions

        update_payload = {
            "properties": {
                "managementGroups": mgmt_groups
            }
        }

        with console.status(f"Importing actions for management group {group_name} in asset {asset_name}..."):
            poller = self.ops.begin_update(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                asset_name=asset_name,
                properties=update_payload
            )
            wait_for_terminal_state(poller, **kwargs)
            asset = self.show(
                asset_name=asset_name,
                namespace_name=namespace["name"],
                resource_group=namespace["resource_group"],
            )
            return _get_sub_property(asset, group_name, property_key="managementGroups")["actions"]

    def _check_device_props(
        self,
        instance_resource_group: str,
        instance_name: str,
        asset_type: Union[List[str], str],  # change to list
        asset_name: Optional[str] = None,
        device_name: Optional[str] = None,
        device_endpoint_name: Optional[str] = None,
        asset: Optional[dict] = None,
        device: Optional[dict] = None,
    ) -> Tuple[dict, Dict[str, str]]:
        """
        Checks the device properties to ensure the endpoint type matches the asset operation's type.
        Returns the asset if the asset name is provided, otherwise the device
        (device name and device endpoint name must be provided).

        This also includes the cluster connectivity check.

        If asset_name is provided (in the case of the asset is already created), it will retrieve the
        asset to populate the device_name and device_endpoint_name. A previously fetched ``asset``
        and/or ``device`` may be passed in to avoid redundant round trips.
        """
        namespace = None
        if asset_name:
            # get the asset to populate the device name and endpoint name
            if asset is None:
                asset = self.show(
                    resource_group=instance_resource_group,
                    instance_name=instance_name,
                    asset_name=asset_name
                )
            device_name = asset["properties"]["deviceRef"]["deviceName"]
            device_endpoint_name = asset["properties"]["deviceRef"]["endpointName"]
            namespace = parse_resource_id(asset["id"])
        else:
            namespace = get_namespace_for_instance(
                cmd=self.cmd,
                instance_name=instance_name,
                instance_resource_group=instance_resource_group
            )

        if device is None:
            device = self.device_ops.get(
                resource_group_name=namespace["resource_group"],
                namespace_name=namespace["name"],
                device_name=device_name
            )

        # use the device to check cluster connectivity
        check_cluster_connectivity(self.cmd, device)

        # ensure device has the endpoint
        device_endpoint = device["properties"].get("endpoints", {}).get("inbound", {}).get(device_endpoint_name)
        if not device_endpoint:
            raise InvalidArgumentValueError(
                f"Device endpoint '{device_endpoint_name}' not found in device '{device_name}'."
            )

        if isinstance(asset_type, str):
            asset_type = [asset_type]

        # asset type must be the same as endpoint type unless either is custom
        device_type_list = [d.lower() for d in DeviceEndpointType.list()]
        allowed = True
        for at in asset_type:
            if (
                at.lower() in device_type_list
                and device_endpoint["endpointType"].lower() in device_type_list
                and at.lower() != device_endpoint["endpointType"].lower()
            ):
                allowed = False
                break

        # we could also change this to a y/n warning prompt
        if not allowed:
            raise InvalidArgumentValueError(
                f"Device endpoint '{device_endpoint_name}' is of type '{device_endpoint['endpointType']}', "
                f"but expected '{' or '.join(asset_type)}'."
            )

        return (asset if asset_name else device, namespace)


def _deep_merge_template(template, existing):
    """Recursively merge existing values into a schema template dict.

    Existing values take precedence over template values. When both values are dicts,
    merge recursively; otherwise return the existing value (unless it is None, in which
    case the template value is kept). Keys present in existing but absent from template
    are added as-is.
    """
    if not isinstance(template, dict) or not isinstance(existing, dict):
        return existing if existing is not None else template
    result = dict(template)
    for key, existing_val in existing.items():
        if key in result:
            result[key] = _deep_merge_template(result[key], existing_val)
        else:
            result[key] = existing_val
    return result


def _merge_destinations_template(template_dests: list, existing_dests: list) -> list:
    """Pre-fill template destinations with existing ARM values, matched by target name.

    Existing destinations whose target is not present in the template are appended as-is so that
    current configuration is preserved and the template stays round-trippable.
    """
    if not existing_dests:
        return template_dests
    existing_by_target = {d.get("target"): d for d in existing_dests if isinstance(d, dict) and d.get("target")}
    matched_targets = set()
    result = []
    for tmpl_dest in template_dests:
        target = tmpl_dest.get("target") if isinstance(tmpl_dest, dict) else None
        existing_dest = existing_by_target.get(target)
        if existing_dest:
            matched_targets.add(target)
            result.append(_deep_merge_template(tmpl_dest, existing_dest))
        else:
            result.append(tmpl_dest)
    for target, existing_dest in existing_by_target.items():
        if target not in matched_targets:
            result.append(existing_dest)
    return result


# Mapping from connector metadata section names to ARM property names and destination paths.
# Each tuple is:
#   (section_key, schema_key, config_prop, dest_path, dest_prop)
# - section_key:  key in the inboundEndpoint metadata dict (e.g. "datasets")
# - schema_key:   key within that section that holds the top-level JSON Schema
# - config_prop:  ARM property name for the configuration (e.g. "defaultDatasetsConfiguration")
# - dest_path:    tuple of keys to traverse into the metadata section to reach the destinations dict
#                 or None if the section has no destinations
# - dest_prop:    ARM property name for the destinations, or None if not applicable
#
# Sections and schema key names are FIXED by the connector metadata JSON Schema
# (additionalProperties: false).  The four supported sections are:
#   datasets       → datasetConfigurationSchema   (sub-item: dataPoints.dataPointConfigurationSchema)
#   eventGroups    → eventGroupConfigurationSchema (sub-item: events.eventConfigurationSchema)
#   streams        → streamConfigurationSchema
#   managementGroups → managementGroupConfigurationSchema (sub-item: managementGroupActions.actionConfigurationSchema)
#
# ARM property names are also fixed and do NOT follow a mechanical pattern from section names
# (e.g. "eventGroups" → "defaultEventsConfiguration", not "defaultEventGroupsConfiguration").
_ASSET_SCHEMA_SECTIONS = [
    (
        "datasets",
        "datasetConfigurationSchema",
        "defaultDatasetsConfiguration",
        ("datasets", "destinations"),
        "defaultDatasetsDestinations",
    ),
    (
        "eventGroups",
        "eventGroupConfigurationSchema",
        "defaultEventsConfiguration",
        ("eventGroups", "events", "destinations"),
        "defaultEventsDestinations",
    ),
    (
        "streams",
        "streamConfigurationSchema",
        "defaultStreamsConfiguration",
        ("streams", "destinations"),
        "defaultStreamsDestinations",
    ),
    (
        "managementGroups",
        "managementGroupConfigurationSchema",
        "defaultManagementGroupsConfiguration",
        None,  # managementGroups has no destinations in the metadata schema
        None,
    ),
]


def _get_metadata_endpoint(metadata: dict, connector_type: str) -> dict:
    """Return the inboundEndpoints entry matching connector_type, or raise ValidationError."""
    from azure.cli.core.azclierror import ValidationError

    for ep in metadata.get("inboundEndpoints", []):
        if ep.get("endpointType", "").lower() == connector_type.lower():
            return ep
    raise ValidationError(
        f"Connector metadata does not contain an inbound endpoint entry for '{connector_type}'."
    )


def _collect_sub_item_schemas(section: dict) -> dict:
    """Scan a metadata section for sub-item *ConfigurationSchema entries and return merged properties.

    For example, eventGroups contains both eventGroupConfigurationSchema (group-level) and
    events.eventConfigurationSchema (event-level). Both sets of fields are valid in the
    defaultEventsConfiguration ARM property, so both should be merged into the template/validation
    schema. This function discovers those sub-item schemas dynamically rather than hardcoding which
    sections have sub-item schemas.
    """
    merged_props: dict = {}
    for value in section.values():
        if not isinstance(value, dict):
            continue
        for sub_key, sub_value in value.items():
            if sub_key.endswith("ConfigurationSchema") and isinstance(sub_value, dict):
                for prop_name, prop_value in sub_value.get("properties", {}).items():
                    if prop_name not in merged_props:
                        merged_props[prop_name] = prop_value
    return merged_props


def _build_destination_template(
    supported_destinations: List[str],
    default_destination: Optional[dict] = None,
    mode: str = "config",
) -> list:
    """Build a destination template list for --show-template output.

    config mode: one entry per supported destination type with null placeholders.
    schema mode: one entry per supported destination showing required fields and types.
    """
    _DEST_FIELDS = {
        "Mqtt": {
            "topic": {"type": "string", "description": "MQTT topic to publish to"},
            "qos": {"type": "string", "enum": ["Qos0", "Qos1"], "description": "MQTT QoS level"},
            "ttl": {"type": "integer", "minimum": 0, "description": "Time to live in seconds"},
            "retain": {"type": "string", "enum": ["Keep", "Never"], "description": "Retain flag"},
        },
        "BrokerStateStore": {
            "key": {"type": "string", "description": "State store key"},
        },
        "Storage": {
            "path": {"type": "string", "description": "Storage path"},
        },
    }

    result = []
    for dest_type in supported_destinations:
        fields = _DEST_FIELDS.get(dest_type, {})
        if mode == "schema":
            entry = {"target": dest_type, "configuration": {}}
            for field_name, field_meta in fields.items():
                entry["configuration"][field_name] = field_meta
        else:
            # config mode: use defaultDestination values if provided, else null
            default_cfg = {}
            if isinstance(default_destination, dict) and default_destination.get("destination") == dest_type:
                default_cfg = {k: v for k, v in default_destination.items() if k != "destination"}
                # Translate metadata-format values to CLI/ARM payload shape:
                # connector metadata uses qos as integer (0/1) and retain as lowercase ("keep"/"never"),
                # but the payload shape requires "Qos0"/"Qos1" and "Keep"/"Never".
                if "qos" in default_cfg and isinstance(default_cfg["qos"], int):
                    default_cfg = {**default_cfg, "qos": f"Qos{default_cfg['qos']}"}
                if "retain" in default_cfg and isinstance(default_cfg["retain"], str):
                    default_cfg = {**default_cfg, "retain": default_cfg["retain"].capitalize()}
            entry = {
                "target": dest_type,
                "configuration": {field: default_cfg.get(field) for field in fields},
            }
        result.append(entry)
    return result


def _build_destination(
    destination_args: List[List[str]],
    allowed_types: Optional[List[str]] = None
) -> List[dict]:
    """
    Builds a destination dictionary for use in assets. The result will be one of the following formats:

    [{
        "target": "BrokerStateStore",
        "configuration": {
            "key": "defaultValue"
        }
    }]

    or

    [{
        "target": "Storage",
        "configuration": {
            "path": "/tmp"
        }
    }]

    or

    [{
        "target": "Mqtt",
        "configuration": {
            "topic": "/contoso/test",
            "retain": "Never",
            "qos": "Qos0",
            "ttl": 3600
        }
    }]

    or [] if no arguments are provided

    Note that this will replace rather than update current destinations. Right now there is support
    for only one destination at a time, but this may change in the future.
    """
    if not destination_args:
        return []

    destination = {}
    destination_args = parse_kvp_nargs(destination_args)
    destination_args_copy = deepcopy(destination_args)
    if "key" in destination_args:
        destination = {
            "target": "BrokerStateStore",
            "configuration": {
                "key": destination_args.pop("key")
            }
        }
    elif "path" in destination_args:
        destination = {
            "target": "Storage",
            "configuration": {
                "path": destination_args.pop("path")
            }
        }
    elif any(
        key in destination_args for key in ["topic", "retain", "qos", "ttl"]
    ):
        if not all(
            key in destination_args for key in ["topic", "retain", "qos", "ttl"]
        ):
            raise RequiredArgumentMissingError(
                "For MQTT destinations, 'topic', 'retain', 'qos', and 'ttl' must be provided."
            )
        from .common import DestinationQos, TopicRetain
        qos = destination_args.pop("qos")
        if qos not in DestinationQos.list():
            raise InvalidArgumentValueError(
                f"Invalid QoS value '{qos}'. Allowed values are: {', '.join(DestinationQos.list())}."
            )
        retain = destination_args.pop("retain")
        if retain not in TopicRetain.list():
            raise InvalidArgumentValueError(
                f"Invalid retain value '{retain}'. Allowed values are: {', '.join(TopicRetain.list())}."
            )

        destination = {
            "target": "Mqtt",
            "configuration": {
                "topic": destination_args.pop("topic"),
                "retain": retain,
                "qos": qos,
                "ttl": int(destination_args.pop("ttl"))
            }
        }
    if allowed_types and destination["target"] not in allowed_types:
        raise InvalidArgumentValueError(
            f"Destination type '{destination['target']}' is not allowed. "
            f"Allowed types are: {', '.join(allowed_types)}."
        )
    if destination_args:
        raise MutuallyExclusiveArgumentError(
            f"Conflicting arguments for destination: {', '.join(destination_args_copy.keys())}\n"
            "For BrokerStateStore, only 'key' is allowed.\n"
            "For Storage, only 'path' is allowed.\n"
            "For Mqtt, all of 'topic', 'retain', 'qos', and 'ttl' are allowed and required."
        )

    return [destination]


def _create_datapoint(
    datapoint_name: str,
    data_source: str,
    type_ref: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    custom_configuration: Optional[str] = None,
) -> dict:
    """Helper function to create a datapoint dictionary."""
    datapoint = {
        "name": datapoint_name,
        "dataSource": data_source,
    }
    if type_ref:
        datapoint["typeRef"] = type_ref

    # if custom configuration is provided, process it and return early
    if custom_configuration:
        datapoint["dataPointConfiguration"] = process_additional_configuration(
            additional_configuration=custom_configuration,
            config_type="datapoint"
        )
        return datapoint

    # otherwise process opcua specific configurations if provided
    additional_configuration = {}
    if queue_size is not None:
        additional_configuration["queueSize"] = queue_size
    if sampling_interval is not None:
        additional_configuration["samplingInterval"] = sampling_interval
    if additional_configuration:
        from .specs import NAMESPACE_ASSET_OPCUA_DATAPOINT_CONFIGURATION_SCHEMA
        ensure_schema_structure(
            NAMESPACE_ASSET_OPCUA_DATAPOINT_CONFIGURATION_SCHEMA, input_data=additional_configuration
        )
    datapoint["dataPointConfiguration"] = json.dumps(additional_configuration)
    # process configurations
    return datapoint


def _create_event(
    event_name: str,
    data_source: Optional[str] = None,
    type_ref: Optional[str] = None,
    queue_size: Optional[int] = None,
    sampling_interval: Optional[int] = None,
    custom_configuration: Optional[str] = None,
    event_destinations: Optional[List[List[str]]] = None,
    condition_refresh: Optional[bool] = None,
) -> dict:
    """Helper function to create an event dictionary."""
    event = {
        "name": event_name,
    }
    if data_source:
        event["dataSource"] = data_source
    if type_ref:
        event["typeRef"] = type_ref
    if event_destinations:
        event["destinations"] = _build_destination(destination_args=event_destinations)

    # if custom configuration is provided, process it and return early
    if custom_configuration:
        event["eventConfiguration"] = process_additional_configuration(
            additional_configuration=custom_configuration,
            config_type="event"
        )
        return event
    additional_configuration = {}
    if queue_size is not None:
        additional_configuration["queueSize"] = queue_size
    if sampling_interval is not None:
        additional_configuration["samplingInterval"] = sampling_interval
    if condition_refresh is not None:
        additional_configuration["conditionRefresh"] = condition_refresh
    if additional_configuration:
        from .specs import NAMESPACE_ASSET_OPCUA_DATAPOINT_CONFIGURATION_SCHEMA
        ensure_schema_structure(
            NAMESPACE_ASSET_OPCUA_DATAPOINT_CONFIGURATION_SCHEMA, input_data=additional_configuration
        )

    event["eventConfiguration"] = json.dumps(additional_configuration)
    # TODO: other event specific configurations can be added here
    return event


def _get_sub_property(asset: dict, name: str, property_key: str) -> dict:
    """Helper function to get a dataset, event groups, or management groups from an asset.

    Raises InvalidArgumentValueError if the subproperty is not found.
    """
    # TODO: could have partial functions (_get_event_group) for ease
    props = asset["properties"].get(property_key, [])
    matched_props = [event for event in props if event["name"] == name]
    # TODO: would we want to prompt user to create if not found?
    if not matched_props:
        property_name = property_key.capitalize()[:-1]
        # deal with managment groups + event groups
        if property_name.endswith("group"):
            property_name = property_name[:-5] + " group"
        raise InvalidArgumentValueError(f"{property_name} '{name}' not found in asset '{asset['name']}'.")
    return matched_props[0]


def _process_configs(
    asset_type: str,
    default: bool = True,
    **kwargs
) -> dict:
    """Main function to process all of the config + destination args based on asset type.

    Destination and custom configuration arguments will be treated as an overwrite rather than update.
    For destinations, currently only one destination is supported but there may be more than one in the future.
    """
    result = {}
    asset_type = asset_type.lower()
    if asset_type == DeviceEndpointType.OPCUA.value.lower():
        # allowed: datasets, events, mgmt groups (no schema?), destinations must be mqtt
        # not allowed: streams
        result = {
            "datasetsConfiguration": _process_opcua_dataset_configurations_v2(
                **kwargs
            ),
            "eventsConfiguration": _process_opcua_event_configurations_v2(
                **kwargs
            ),
            "datasetsDestinations": _build_destination(
                destination_args=kwargs.get("dataset_destinations", []),
                allowed_types=["Mqtt"]
            ),
            "eventsDestinations": _build_destination(
                destination_args=kwargs.get("event_destinations", []),
                allowed_types=["Mqtt"]
            ),
        }
    elif asset_type == DeviceEndpointType.ONVIF.value.lower():
        # allowed: events (no schema), mgmt groups (no schema), destinations must be mqtt
        # not allowed: datasets, streams
        result = {
            "eventsDestinations": _build_destination(
                destination_args=kwargs.get("event_destinations", []),
                allowed_types=["Mqtt"]
            )
        }
    elif asset_type == DeviceEndpointType.MEDIA.value.lower():
        # allowed: streams, destinations can be mqtt or storage
        # not allowed: datasets, events, mgmt groups
        result = {
            "streamsConfiguration": _process_media_stream_configurations(
                **kwargs
            ),
            "streamsDestinations": _build_destination(
                destination_args=kwargs.get("stream_destinations", []),
                allowed_types=["Storage", "Mqtt"]
            )
        }
    elif asset_type == DeviceEndpointType.REST.value.lower():
        # allowed only datasets
        result = {
            "datasetsConfiguration": _process_rest_dataset_configurations(
                **kwargs
            ),
            "datasetsDestinations": _build_destination(
                destination_args=kwargs.get("dataset_destinations", []),
                allowed_types=["BrokerStateStore", "Mqtt"]
            )
        }
    else:
        # Custom - treat everything as an overwrite
        result = {
            "datasetsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("dataset_custom_configuration"),
                config_type="dataset"
            ),
            "eventsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("event_custom_configuration"),
                config_type="event"
            ),
            "managementGroupsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("mgmt_custom_configuration"),
                config_type="management group"
            ),
            "streamsConfiguration": process_additional_configuration(
                additional_configuration=kwargs.get("stream_custom_configuration"),
                config_type="stream"
            ),
            "datasetsDestinations": _build_destination(
                destination_args=kwargs.get("dataset_destinations", []),
            ),
            "eventsDestinations": _build_destination(
                destination_args=kwargs.get("event_destinations", []),
            ),
            "streamsDestinations": _build_destination(
                destination_args=kwargs.get("stream_destinations", []),
            )
        }

    # if default, captalize and add in "default" to key
    if default:
        for key in list(result.keys()):
            # Capitalize the first letter of OG key
            new_key = "default" + key[0].upper() + key[1:]
            result[new_key] = result.pop(key)

    # pop empty values:
    result = {k: v for k, v in result.items() if v}
    return result


def _process_opcua_dataset_configurations_v1(
    original_dataset_configuration: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    opcua_dataset_start_instance: Optional[str] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V1

    result = json.loads(original_dataset_configuration) if original_dataset_configuration else {}
    if opcua_dataset_publishing_interval is not None:
        result["publishingInterval"] = opcua_dataset_publishing_interval
    if opcua_dataset_sampling_interval is not None:
        result["samplingInterval"] = opcua_dataset_sampling_interval
    if opcua_dataset_queue_size is not None:
        result["queueSize"] = opcua_dataset_queue_size
    if opcua_dataset_key_frame_count is not None:
        result["keyFrameCount"] = opcua_dataset_key_frame_count
    if opcua_dataset_start_instance is not None:
        result["startInstance"] = opcua_dataset_start_instance

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V1,
        input_data=result
    )
    return json.dumps(result)


def _process_opcua_dataset_configurations_v2(
    original_dataset_configuration: Optional[str] = None,
    opcua_dataset_publishing_interval: Optional[int] = None,
    opcua_dataset_sampling_interval: Optional[int] = None,
    opcua_dataset_queue_size: Optional[int] = None,
    opcua_dataset_key_frame_count: Optional[int] = None,
    opcua_dataset_start_instance: Optional[str] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V2
    result = json.loads(original_dataset_configuration) if original_dataset_configuration else {}
    if opcua_dataset_publishing_interval is not None:
        result["publishingInterval"] = opcua_dataset_publishing_interval
    if opcua_dataset_sampling_interval is not None:
        result["samplingInterval"] = opcua_dataset_sampling_interval
    if opcua_dataset_queue_size is not None:
        result["queueSize"] = opcua_dataset_queue_size
    if opcua_dataset_key_frame_count is not None:
        result["keyFrameCount"] = opcua_dataset_key_frame_count
    if opcua_dataset_start_instance is not None:
        result["startInstance"] = opcua_dataset_start_instance

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V2,
        input_data=result
    )
    return json.dumps(result)


def _process_opcua_event_configurations_v1(
    original_event_configuration: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    opcua_event_start_instance: Optional[str] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V1

    result = json.loads(original_event_configuration) if original_event_configuration else {}
    if opcua_event_publishing_interval is not None:
        result["publishingInterval"] = opcua_event_publishing_interval
    if opcua_event_queue_size is not None:
        result["queueSize"] = opcua_event_queue_size
    if opcua_event_start_instance is not None:
        result["startInstance"] = opcua_event_start_instance

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V1,
        input_data=result
    )
    return json.dumps(result)


def _process_opcua_event_configurations_v2(
    original_event_configuration: Optional[str] = None,
    opcua_event_publishing_interval: Optional[int] = None,
    opcua_event_queue_size: Optional[int] = None,
    opcua_event_start_instance: Optional[str] = None,
    opcua_event_filter_type: Optional[str] = None,
    opcua_event_filter_clauses: Optional[List[List[str]]] = None,  # path (req), type, field
    opcua_event_condition_refresh_interval: Optional[int] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V2

    result = json.loads(original_event_configuration) if original_event_configuration else {}
    if opcua_event_publishing_interval is not None:
        result["publishingInterval"] = opcua_event_publishing_interval
    if opcua_event_queue_size is not None:
        result["queueSize"] = opcua_event_queue_size
    if opcua_event_start_instance is not None:
        result["startInstance"] = opcua_event_start_instance
    if opcua_event_condition_refresh_interval is not None:
        result["conditionRefreshInterval"] = opcua_event_condition_refresh_interval

    if opcua_event_filter_type or opcua_event_filter_clauses:
        result["eventFilter"] = {}
    if opcua_event_filter_type is not None:
        result["eventFilter"]["typeDefinitionId"] = opcua_event_filter_type
    if opcua_event_filter_clauses:
        result["eventFilter"]["selectClauses"] = []
        for clause in opcua_event_filter_clauses or []:
            clause = parse_kvp_nargs(clause)
            if "path" not in clause:
                logger.warning(
                    f"Skipping event filter clause '{clause}', it must contain a 'path' key."
                )
                continue
            formatted_clause = {"browsePath": clause["path"]}
            if "type" in clause:
                formatted_clause["typeDefinitionId"] = clause.get("type")
            if "field" in clause:
                formatted_clause["fieldId"] = clause.get("field")
            result["eventFilter"]["selectClauses"].append(formatted_clause)

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V2,
        input_data=result
    )
    return json.dumps(result)


def _process_media_stream_configurations(
    original_stream_configuration: Optional[str] = None,
    task_type: Optional[str] = None,
    disable_autostart: Optional[bool] = None,
    task_format: Optional[str] = None,
    snapshots_per_second: Optional[int] = None,
    path: Optional[str] = None,
    duration: Optional[int] = None,
    media_server_address: Optional[str] = None,
    media_server_path: Optional[str] = None,
    media_server_port: Optional[int] = None,
    media_server_username: Optional[str] = None,
    media_server_password: Optional[str] = None,
    media_server_certificate: Optional[str] = None,
    **_
) -> str:
    from .specs import (
        NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA,
        MediaFormat,
        MediaTaskType,
    )
    result = json.loads(original_stream_configuration) if original_stream_configuration else {}

    task_type = task_type or result.get("taskType")
    if not task_type:
        if not any([
            task_format, disable_autostart, snapshots_per_second, path, duration,
            media_server_address, media_server_path, media_server_port,
            media_server_username, media_server_password, media_server_certificate
        ]):
            return original_stream_configuration
        else:
            raise RequiredArgumentMissingError(
                "Task type via --task-type must be provided when configuring media stream properties."
            )
    allowed_properties = MediaTaskType(task_type).allowed_properties

    # empty result if changing task type
    if result.get("taskType") and task_type != result.get("taskType"):
        logger.warning("Changing Media Stream Configuration task type, resetting configuration.")
        result = {}

    # Process provided parameters and update result
    for property_name, param_value in {
        "autostart": disable_autostart,
        "format": task_format,
        "snapshotsPerSecond": snapshots_per_second,
        "path": path,
        "duration": duration,
        "mediaServerAddress": media_server_address,
        "mediaServerPath": media_server_path,
        "mediaServerPort": media_server_port,
        "mediaServerUsernameRef": media_server_username,
        "mediaServerPasswordRef": media_server_password,
        "mediaServerCertificateRef": media_server_certificate
    }.items():
        # Skip None values
        if param_value is None:
            continue
        if property_name == "autostart":
            param_value = not param_value  # Convert to 'enabled' property

        # Check if this property is allowed for the current task type
        if property_name not in allowed_properties:
            raise InvalidArgumentValueError(
                f"Property '{property_name}' is not allowed for task type '{task_type}'. "
                f"Allowed properties: {allowed_properties}"
            )

        # Validate format based on the task type
        if property_name == "format" and param_value:
            format_enum = MediaFormat(param_value)
            # Validate format for clip tasks
            if task_type == MediaTaskType.clip_to_fs.value:
                if not format_enum.allowed_for_clip:
                    clip_formats = [
                        f.value for f in MediaFormat
                        if MediaFormat(f.value).allowed_for_clip
                    ]
                    raise InvalidArgumentValueError(
                        f"Invalid format for clip task: '{param_value}'. "
                        f"Valid formats: {clip_formats}"
                    )
            # Validate format for snapshot tasks
            else:
                if not format_enum.allowed_for_snapshot:
                    snapshot_formats = [
                        f.value for f in MediaFormat
                        if MediaFormat(f.value).allowed_for_snapshot
                    ]
                    raise InvalidArgumentValueError(
                        f"Invalid format for snapshot task: '{param_value}'. "
                        f"Valid formats: {snapshot_formats}"
                    )

        # Apply the value to the result
        result[property_name] = param_value

    result["taskType"] = MediaTaskType(task_type).value
    # Final schema validation
    ensure_schema_structure(
        schema=NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA,
        input_data=result
    )
    return json.dumps(result)


def _process_rest_dataset_configurations(
    original_dataset_configuration: Optional[str] = None,
    rest_dataset_sampling_interval: Optional[int] = None,
    **_
) -> str:
    from .specs import NAMESPACE_ASSET_REST_DATASET_CONFIGURATION_SCHEMA

    result = json.loads(original_dataset_configuration) if original_dataset_configuration else {}
    if rest_dataset_sampling_interval is not None:
        result["samplingIntervalInMilliseconds"] = rest_dataset_sampling_interval

    ensure_schema_structure(
        schema=NAMESPACE_ASSET_REST_DATASET_CONFIGURATION_SCHEMA,
        input_data=result
    )
    return json.dumps(result)


def _update_asset_props(
    properties: dict,
    asset_type_refs: Optional[List[str]] = None,
    attributes: Optional[List[str]] = None,
    description: Optional[str] = None,
    disabled: Optional[bool] = None,
    discovered_asset_refs: Optional[List[str]] = None,
    display_name: Optional[str] = None,
    documentation_uri: Optional[str] = None,
    external_asset_id: Optional[str] = None,
    hardware_revision: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_uri: Optional[str] = None,
    model: Optional[str] = None,
    product_code: Optional[str] = None,
    serial_number: Optional[str] = None,
    software_revision: Optional[str] = None,
):
    # TODO: currently max num of asset type ref is 1
    if asset_type_refs:
        properties["assetTypeRefs"] = asset_type_refs
    if attributes:
        properties["attributes"] = parse_kvp_nargs(attributes)
    if description:
        properties["description"] = description
    if disabled is not None:
        properties["enabled"] = not disabled
    if discovered_asset_refs:
        properties["discoveredAssetRefs"] = discovered_asset_refs
    if display_name:
        properties["displayName"] = display_name
    if documentation_uri:
        properties["documentationUri"] = documentation_uri
    if external_asset_id:
        properties["externalAssetId"] = external_asset_id
    if hardware_revision:
        properties["hardwareRevision"] = hardware_revision
    if manufacturer:
        properties["manufacturer"] = manufacturer
    if manufacturer_uri:
        properties["manufacturerUri"] = manufacturer_uri
    if model:
        properties["model"] = model
    if product_code:
        properties["productCode"] = product_code
    if serial_number:
        properties["serialNumber"] = serial_number
    if software_revision:
        properties["softwareRevision"] = software_revision


def _process_namespace_sub_points_file_path(
    file_path: str,
    original_items: Optional[List[dict]] = None,
    point_key: Optional[str] = None,
    replace: bool = False,
    csv_converter=None
) -> List[Dict[str, str]]:
    """Merge items from file with existing items."""
    from ...util import deserialize_file_content

    file_points = list(deserialize_file_content(file_path=file_path))

    if file_path.endswith('.csv'):
        if csv_converter:
            csv_converter(file_points)
        else:
            raise InvalidArgumentValueError("CSV conversion not supported for this operation.")

    if point_key is None:
        return file_points

    if not original_items:
        original_items = []

    original_points = {point[point_key]: point for point in original_items}
    file_points_dict = {point[point_key]: point for point in file_points}

    skipped_keys = []
    for key in file_points_dict:
        if key in original_points and not replace:
            skipped_keys.append(key)
        else:
            original_points[key] = file_points_dict[key]

    if skipped_keys:
        logger.warning(
            f"The following entries are already present in the asset and will be ignored: "
            f"{', '.join(str(k) for k in skipped_keys)}"
        )

    return list(original_points.values())
