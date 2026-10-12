import re
import sys
from collections import OrderedDict
from typing import Optional
from urllib.parse import quote, urljoin, urlsplit

from azure.cli.core.azclierror import AzureResponseError, InvalidArgumentValueError, ValidationError
from azure.cli.core.commands.client_factory import get_subscription_id
from azure.cli.core.util import send_raw_request
from knack.log import get_logger

from ....util.machinery import scoped_semver_import
from ....util.oci_client import get_oci_client
from ..runtime import OperationRequirements
from ..runtime_profiles import RuntimeChannel


logger = get_logger(__name__)

CONNECTOR_DISCOVERY_REQUIREMENT = OperationRequirements("Connector discovery", channels={RuntimeChannel.PREVIEW})
MARKETPLACE_URL = (
    "https://marketplace.microsoft.com/en-us/search/products"
    "?search=iot%20operations"
)
FIRST_PARTY_CONNECTOR_NAMES = ("rest", "media", "mqtt", "sse", "onvif")


def sorted_connector_versions(tags: list) -> list:
    semver = scoped_semver_import()
    versions = []
    for tag in sorted(set(tags)):
        try:
            versions.append((semver.parse(tag), tag))
        except ValueError:
            continue
    return [tag for _, tag in sorted(versions, reverse=True)]


def validate_metadata_reference(metadata_ref: str) -> None:
    if not isinstance(metadata_ref, str) or not re.fullmatch(
        r"(?:[a-zA-Z0-9-]+\.)+[a-zA-Z0-9-]+/[\w./-]+-metadata:[a-zA-Z0-9._-]+", metadata_ref
    ):
        raise InvalidArgumentValueError(
            "Expected a fully qualified metadata reference: registry.example.com/path/connector-metadata:tag."
        )


def metadata_supports_runtime(metadata: dict, runtime_version: str) -> bool:
    semver = scoped_semver_import()
    try:
        runtime = semver.parse(runtime_version)
    except (ValueError, TypeError) as error:
        raise ValidationError("Cannot determine the target AIO runtime version.") from error
    requirements = metadata.get("aioMetadata") if isinstance(metadata, dict) else None
    if not isinstance(requirements, dict) or not requirements.get("aioMinVersion"):
        raise ValidationError("Connector metadata must declare aioMetadata.aioMinVersion to establish compatibility.")
    try:
        minimum = semver.parse(requirements["aioMinVersion"])
        if "aioMaxVersion" not in requirements:
            return runtime >= minimum
        maximum = requirements["aioMaxVersion"]
        if not isinstance(maximum, str):
            raise ValueError("Invalid maximum version")
        if "*" in maximum:
            if not re.fullmatch(r"(?:0|[1-9][0-9]*|\*)\.(?:0|[1-9][0-9]*|\*)\.(?:0|[1-9][0-9]*|\*)", maximum):
                raise ValueError("Invalid wildcard maximum version")
            components = maximum.split(".")
            wildcard_index = components.index("*")
            if any(part != "*" for part in components[wildcard_index:]):
                raise ValueError("Invalid wildcard maximum version")
            prefix = tuple(int(part) for part in components[:wildcard_index])
            if (minimum.major, minimum.minor)[:len(prefix)] > prefix:
                raise ValueError("Maximum is below minimum")
            return runtime >= minimum and (runtime.major, runtime.minor)[:len(prefix)] <= prefix
        maximum_version = semver.parse(maximum)
        if maximum_version < minimum:
            raise ValueError("Maximum is below minimum")
        return minimum <= runtime <= maximum_version
    except (ValueError, TypeError) as error:
        raise ValidationError("Connector metadata declares an invalid AIO compatibility range.") from error


def get_first_party_connectors(cmd, runtime_version: str) -> tuple:
    from .connector_templates import ConnectorTemplates

    entries = []
    registry = get_oci_client()
    for name in FIRST_PARTY_CONNECTOR_NAMES:
        repository = f"mcr.microsoft.com/azureiotoperations/akri-connectors/{name}-metadata"
        for version in sorted_connector_versions(registry.list_tags(repository, cmd=cmd)):
            reference = f"{repository}:{version}"
            metadata = show_connector(cmd, reference)["metadata"]
            try:
                compatible = metadata_supports_runtime(metadata, runtime_version)
            except ValidationError as error:
                raise ValidationError(f"Cannot determine compatibility for {reference}: {error}") from error
            if compatible:
                ConnectorTemplates._validate_metadata(metadata, reference)
                entries.append((name, reference))
                break
    return tuple(entries)


def require_preview_instance(cmd, instance_name: str, resource_group_name: str) -> str:
    from .instances import Instances
    from ..runtime_catalog import get_runtime_catalog

    runtime = vars(cmd).get("runtime_context")
    if runtime is None:
        instances = Instances(cmd)
        instance = instances.show(name=instance_name, resource_group_name=resource_group_name)
        runtime = instances.get_runtime_context(
            instance, get_runtime_catalog().qualification_identities, allow_unbundled_integration=True,
        )
    CONNECTOR_DISCOVERY_REQUIREMENT.validate(runtime)
    return runtime.instance_id


class Connectors:
    def __init__(self, cmd, api_version: Optional[str] = None):
        from ..runtime_catalog import get_runtime_catalog

        self.cmd = cmd
        self.runtime_profile = get_runtime_catalog().get(RuntimeChannel.PREVIEW)
        self.api_version = (
            api_version if api_version is not None
            else self.runtime_profile.iotops_api_version
        )
        self.arm_endpoint = cmd.cli_ctx.cloud.endpoints.resource_manager.rstrip("/")

    def _get_instance_id(self, instance_name: str, resource_group_name: str) -> str:
        instance_id = require_preview_instance(self.cmd, instance_name, resource_group_name)
        subscription_id = get_subscription_id(self.cmd.cli_ctx)
        expected_id = (
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.IoTOperations/instances/{instance_name}"
        )
        if instance_id.lower() != expected_id.lower():
            raise ValidationError("The resolved instance does not match the requested instance and subscription.")
        return instance_id

    def list(self, instance_name: str, resource_group_name: str) -> list:
        instance_id = self._get_instance_id(instance_name, resource_group_name)
        result = self.list_available(instance_id)
        self._show_marketplace_hint()
        return result

    def show(self, instance_name: str, resource_group_name: str, metadata_ref: str) -> dict:
        validate_metadata_reference(metadata_ref)
        self._get_instance_id(instance_name, resource_group_name)
        return show_connector(self.cmd, metadata_ref)

    def list_available(self, instance_id: str) -> list:
        """Read definitions for a runtime-validated instance using the CLI preview profile."""
        collection = f"{self.arm_endpoint}{quote(instance_id, safe='/')}/aioApplicationDefinitions"
        url = f"{collection}?api-version={quote(self.api_version, safe='')}"
        visited = set()
        marketplace = []
        while url:
            if url in visited:
                raise AzureResponseError("Connector definition pagination returned a repeated nextLink.")
            visited.add(url)
            response = send_raw_request(cli_ctx=self.cmd.cli_ctx, method="GET", url=url)
            try:
                page = response.json()
            except ValueError as error:
                raise AzureResponseError("Connector definition discovery returned invalid JSON.") from error
            if not isinstance(page, dict) or not isinstance(page.get("value"), list):
                raise AzureResponseError("Connector definition discovery returned an invalid list response.")
            for definition in page["value"]:
                if not isinstance(definition, dict) or not isinstance(definition.get("properties"), dict):
                    raise AzureResponseError("Connector definition discovery returned an invalid definition.")
                properties = definition["properties"]
                source, application_type = properties.get("applicationSource"), properties.get("applicationType")
                if (
                    not isinstance(source, str) or source.lower() != "marketplace"
                    or not isinstance(application_type, str) or application_type.lower() != "connector"
                ):
                    continue
                name = definition.get("name")
                reference = properties.get("applicationMetadataRef")
                if not isinstance(name, str) or not name:
                    raise AzureResponseError("Connector definition discovery returned a definition without a name.")
                try:
                    validate_metadata_reference(reference)
                except InvalidArgumentValueError as error:
                    raise AzureResponseError(
                        "A connector definition did not provide a fully qualified applicationMetadataRef."
                    ) from error
                marketplace.append({"name": name, "source": "Marketplace", "metadataRef": reference})
            next_link = page.get("nextLink")
            if next_link is None or next_link == "":
                break
            if not isinstance(next_link, str):
                raise AzureResponseError("Connector definition discovery returned an invalid nextLink.")
            next_url = urljoin(url, next_link)
            parsed = urlsplit(next_url)
            expected = urlsplit(collection)
            if (
                parsed.scheme != expected.scheme or parsed.netloc != expected.netloc
                or parsed.path.lower() != expected.path.lower() or parsed.fragment
            ):
                raise AzureResponseError("Connector definition discovery returned a nextLink outside the collection.")
            url = next_url
        first_party = []
        for name, reference in get_first_party_connectors(self.cmd, self.runtime_profile.identity.version):
            first_party.append({"name": name, "source": "FirstParty", "metadataRef": reference})
        return first_party + marketplace

    def _show_marketplace_hint(self) -> None:
        cli_ctx = self.cmd.cli_ctx
        output = cli_ctx.invocation.data.get("output", cli_ctx.config.get("core", "output", fallback="json"))
        if (
            not sys.stdout.isatty() or not sys.stderr.isatty()
            or getattr(cli_ctx, "only_show_errors", False)
            or output == "none"
        ):
            return
        logger.warning("Purchase additional connectors in Azure Marketplace: %s", MARKETPLACE_URL)


def show_connector(cmd, metadata_ref: str) -> dict:
    from .connector_templates import ConnectorTemplates

    validate_metadata_reference(metadata_ref)
    metadata = ConnectorTemplates.fetch_metadata(cmd, metadata_ref)
    if not isinstance(metadata, dict):
        raise ValidationError("Connector metadata must be a JSON object.")
    return {"metadataRef": metadata_ref, "metadata": metadata}


def connector_list_table(result: list) -> list:
    return [OrderedDict([
        ("Name", entry.get("name")),
        ("Source", entry.get("source")),
        ("MetadataRef", entry.get("metadataRef")),
    ]) for entry in result]


def connector_show_table(result: dict) -> OrderedDict:
    metadata = result.get("metadata", {})
    return OrderedDict([
        ("Name", metadata.get("name")),
        ("Version", metadata.get("version")),
        ("MetadataRef", result.get("metadataRef")),
    ])
