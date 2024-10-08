# coding=utf-8
# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# Code generated by Microsoft (R) AutoRest Code Generator.
# Changes may cause incorrect behavior and will be lost if the code is regenerated.
# --------------------------------------------------------------------------

from copy import deepcopy
from typing import Any, TYPE_CHECKING

from azure.core.rest import HttpRequest, HttpResponse
from azure.mgmt.core import ARMPipelineClient

from ._configuration import MicrosoftDeviceRegistryManagementServiceConfiguration
from ._serialization import Deserializer, Serializer
from .operations import (
    AssetEndpointProfilesOperations,
    AssetsOperations,
    BillingContainersOperations,
    DiscoveredAssetEndpointProfilesOperations,
    DiscoveredAssetsOperations,
    OperationStatusOperations,
    Operations,
    SchemaRegistriesOperations,
    SchemaVersionsOperations,
    SchemasOperations,
)

if TYPE_CHECKING:
    # pylint: disable=unused-import,ungrouped-imports
    from azure.core.credentials import TokenCredential


class MicrosoftDeviceRegistryManagementService:  # pylint: disable=client-accepts-api-version-keyword,too-many-instance-attributes
    """Microsoft.DeviceRegistry Resource Provider management API.

    :ivar operations: Operations operations
    :vartype operations: deviceregistry.mgmt.operations.Operations
    :ivar asset_endpoint_profiles: AssetEndpointProfilesOperations operations
    :vartype asset_endpoint_profiles:
     deviceregistry.mgmt.operations.AssetEndpointProfilesOperations
    :ivar assets: AssetsOperations operations
    :vartype assets: deviceregistry.mgmt.operations.AssetsOperations
    :ivar billing_containers: BillingContainersOperations operations
    :vartype billing_containers: deviceregistry.mgmt.operations.BillingContainersOperations
    :ivar discovered_asset_endpoint_profiles: DiscoveredAssetEndpointProfilesOperations operations
    :vartype discovered_asset_endpoint_profiles:
     deviceregistry.mgmt.operations.DiscoveredAssetEndpointProfilesOperations
    :ivar discovered_assets: DiscoveredAssetsOperations operations
    :vartype discovered_assets: deviceregistry.mgmt.operations.DiscoveredAssetsOperations
    :ivar operation_status: OperationStatusOperations operations
    :vartype operation_status: deviceregistry.mgmt.operations.OperationStatusOperations
    :ivar schema_registries: SchemaRegistriesOperations operations
    :vartype schema_registries: deviceregistry.mgmt.operations.SchemaRegistriesOperations
    :ivar schemas: SchemasOperations operations
    :vartype schemas: deviceregistry.mgmt.operations.SchemasOperations
    :ivar schema_versions: SchemaVersionsOperations operations
    :vartype schema_versions: deviceregistry.mgmt.operations.SchemaVersionsOperations
    :param subscription_id: The ID of the target subscription. The value must be an UUID. Required.
    :type subscription_id: str
    :param credential: Credential needed for the client to connect to Azure. Required.
    :type credential: ~azure.core.credentials.TokenCredential
    :keyword endpoint: Service URL. Default value is "https://management.azure.com".
    :paramtype endpoint: str
    :keyword api_version: Api Version. Default value is "2024-09-01-preview". Note that overriding
     this default value may result in unsupported behavior.
    :paramtype api_version: str
    :keyword int polling_interval: Default waiting time between two polls for LRO operations if no
     Retry-After header is present.
    """

    def __init__(
        self,
        subscription_id: str,
        credential: "TokenCredential",
        *,
        endpoint: str = "https://management.azure.com",
        **kwargs: Any
    ) -> None:
        self._config = MicrosoftDeviceRegistryManagementServiceConfiguration(
            subscription_id=subscription_id, credential=credential, **kwargs
        )
        self._client: ARMPipelineClient = ARMPipelineClient(base_url=endpoint, config=self._config, **kwargs)

        self._serialize = Serializer()
        self._deserialize = Deserializer()
        self._serialize.client_side_validation = False
        self.operations = Operations(self._client, self._config, self._serialize, self._deserialize)
        self.asset_endpoint_profiles = AssetEndpointProfilesOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.assets = AssetsOperations(self._client, self._config, self._serialize, self._deserialize)
        self.billing_containers = BillingContainersOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.discovered_asset_endpoint_profiles = DiscoveredAssetEndpointProfilesOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.discovered_assets = DiscoveredAssetsOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.operation_status = OperationStatusOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.schema_registries = SchemaRegistriesOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.schemas = SchemasOperations(self._client, self._config, self._serialize, self._deserialize)
        self.schema_versions = SchemaVersionsOperations(self._client, self._config, self._serialize, self._deserialize)

    def send_request(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        """Runs the network request through the client's chained policies.

        >>> from azure.core.rest import HttpRequest
        >>> request = HttpRequest("GET", "https://www.example.org/")
        <HttpRequest [GET], url: 'https://www.example.org/'>
        >>> response = client.send_request(request)
        <HttpResponse: 200 OK>

        For more information on this code flow, see https://aka.ms/azsdk/dpcodegen/python/send_request

        :param request: The network request you want to make. Required.
        :type request: ~azure.core.rest.HttpRequest
        :keyword bool stream: Whether the response payload will be streamed. Defaults to False.
        :return: The response of your network call. Does not do error handling on your response.
        :rtype: ~azure.core.rest.HttpResponse
        """

        request_copy = deepcopy(request)
        request_copy.url = self._client.format_url(request_copy.url)
        return self._client.send_request(request_copy, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MicrosoftDeviceRegistryManagementService":
        self._client.__enter__()
        return self

    def __exit__(self, *exc_details: Any) -> None:
        self._client.__exit__(*exc_details)
