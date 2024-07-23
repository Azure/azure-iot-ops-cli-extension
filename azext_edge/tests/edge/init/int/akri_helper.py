# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from ....helpers import get_kubectl_workload_items


def assert_akri_args(
    namespace: str,
    kubernetes_distro: Optional[str] = None,
    **_
):
    kubernetes_distro = kubernetes_distro or "k8s"

    # get akri pods
    akri_pods = get_kubectl_workload_items(
        prefixes="aio-akri-", service_type="pod", namespace=namespace
    )

    for pod_value in akri_pods.values():
        assert kubernetes_distro in pod_value["spec"]["nodeName"]
