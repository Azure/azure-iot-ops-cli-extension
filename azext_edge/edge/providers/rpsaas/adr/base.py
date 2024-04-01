# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger

from ..base_provider import RPSaaSBaseProvider
from ....common import ClusterExtensionsMapping, ResourceProviderMapping

logger = get_logger(__name__)
ADR_API_VERSION = "2023-11-01-preview"


class ADRBaseProvider(RPSaaSBaseProvider):
    def __init__(
        self, cmd, resource_type: str
    ):
        super(ADRBaseProvider, self).__init__(
            cmd=cmd,
            api_version=ADR_API_VERSION,
            provider_namespace=ResourceProviderMapping.deviceregistry.value,
            resource_type=resource_type,
            required_extension=ClusterExtensionsMapping.asset.value
        )
