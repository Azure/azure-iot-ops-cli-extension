# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from .base import EdgeResourceApi
from ...common import ListableEnum


class KeyVaultResourceKinds(ListableEnum):
    SECRET_PROVIDER_CLASS = "secretproviderclass"
    SECRET_PROVIDER_CLASS_POD_STATUS = "secretproviderclasspodstatus"


KEYVAULT_API_V1 = EdgeResourceApi(group="secrets-store.csi.x-k8s.io", version="v1", moniker="keyvault")
