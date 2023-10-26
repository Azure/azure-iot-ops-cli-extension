# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


def get_kv_secret_store_yaml(name: str, namespace: str, keyvault_name: str, secret_name: str, tenantId: str) -> dict:
    from yaml import safe_load

    return safe_load(
        f"""
    apiVersion: secrets-store.csi.x-k8s.io/v1
    kind: SecretProviderClass
    metadata:
      name: {name}
      namespace: {namespace}
    spec:
      provider: "azure"
      parameters:
        usePodIdentity: "false"
        keyvaultName: "{keyvault_name}"
        objects: |
          array:
            - |
              objectName: {secret_name}
              objectType: secret
              objectVersion: ""
        tenantId: {tenantId}
    """
    )
