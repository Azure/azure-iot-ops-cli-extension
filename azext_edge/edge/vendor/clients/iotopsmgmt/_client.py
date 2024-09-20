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

from ._configuration import MicrosoftIoTOperationsManagementServiceConfiguration
from ._serialization import Deserializer, Serializer
from .operations import (
    BrokerAuthenticationOperations,
    BrokerAuthorizationOperations,
    BrokerListenerOperations,
    BrokerOperations,
    DataflowEndpointOperations,
    DataflowOperations,
    DataflowProfileOperations,
    InstanceOperations,
    Operations,
)

if TYPE_CHECKING:
    # pylint: disable=unused-import,ungrouped-imports
    from azure.core.credentials import TokenCredential


class MicrosoftIoTOperationsManagementService:  # pylint: disable=too-many-instance-attributes
    """Microsoft.IoTOperations Resource Provider management API.

    :ivar operations: Operations operations
    :vartype operations: aziotops.mgmt.operations.Operations
    :ivar instance: InstanceOperations operations
    :vartype instance: aziotops.mgmt.operations.InstanceOperations
    :ivar broker: BrokerOperations operations
    :vartype broker: aziotops.mgmt.operations.BrokerOperations
    :ivar broker_authentication: BrokerAuthenticationOperations operations
    :vartype broker_authentication: aziotops.mgmt.operations.BrokerAuthenticationOperations
    :ivar broker_authorization: BrokerAuthorizationOperations operations
    :vartype broker_authorization: aziotops.mgmt.operations.BrokerAuthorizationOperations
    :ivar broker_listener: BrokerListenerOperations operations
    :vartype broker_listener: aziotops.mgmt.operations.BrokerListenerOperations
    :ivar dataflow_endpoint: DataflowEndpointOperations operations
    :vartype dataflow_endpoint: aziotops.mgmt.operations.DataflowEndpointOperations
    :ivar dataflow_profile: DataflowProfileOperations operations
    :vartype dataflow_profile: aziotops.mgmt.operations.DataflowProfileOperations
    :ivar dataflow: DataflowOperations operations
    :vartype dataflow: aziotops.mgmt.operations.DataflowOperations
    :param subscription_id: The ID of the target subscription. The value must be an UUID. Required.
    :type subscription_id: str
    :param credential: Credential needed for the client to connect to Azure. Required.
    :type credential: ~azure.core.credentials.TokenCredential
    :keyword endpoint: Service URL. Default value is "https://management.azure.com".
    :paramtype endpoint: str
    :keyword api_version: Api Version. Default value is "2024-08-15-preview". Note that overriding
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
        self._config = MicrosoftIoTOperationsManagementServiceConfiguration(
            subscription_id=subscription_id, credential=credential, **kwargs
        )
        self._client: ARMPipelineClient = ARMPipelineClient(base_url=endpoint, config=self._config, **kwargs)

        self._serialize = Serializer()
        self._deserialize = Deserializer()
        self._serialize.client_side_validation = False
        self.operations = Operations(self._client, self._config, self._serialize, self._deserialize)
        self.instance = InstanceOperations(self._client, self._config, self._serialize, self._deserialize)
        self.broker = BrokerOperations(self._client, self._config, self._serialize, self._deserialize)
        self.broker_authentication = BrokerAuthenticationOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.broker_authorization = BrokerAuthorizationOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.broker_listener = BrokerListenerOperations(self._client, self._config, self._serialize, self._deserialize)
        self.dataflow_endpoint = DataflowEndpointOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.dataflow_profile = DataflowProfileOperations(
            self._client, self._config, self._serialize, self._deserialize
        )
        self.dataflow = DataflowOperations(self._client, self._config, self._serialize, self._deserialize)

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

    def __enter__(self) -> "MicrosoftIoTOperationsManagementService":
        self._client.__enter__()
        return self

    def __exit__(self, *exc_details: Any) -> None:
        self._client.__exit__(*exc_details)
