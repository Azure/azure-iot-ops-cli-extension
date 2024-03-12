# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from kubernetes import client
from kubernetes.client.exceptions import ApiException
from typing import Optional

logger = get_logger(__name__)
generic = client.ApiClient()


def get_bindings(field_selector: str) -> Optional[dict]:
    try:
        v1_auth_client = client.RbacAuthorizationV1Api()
        result = v1_auth_client.list_cluster_role_binding(field_selector=field_selector)
    except ApiException as ae:
        logger.debug(msg=str(ae))
        if int(ae.status) == 404:
            return
        raise ae
    else:
        if result:
            return generic.sanitize_for_serialization(obj=result)
