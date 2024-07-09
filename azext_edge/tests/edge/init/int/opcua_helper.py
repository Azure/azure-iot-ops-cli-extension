# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from ....helpers import get_kubectl_workload_items


def assert_simulate_plc_args(
    namespace: str,
    simulate_plc: Optional[bool] = None,
    **_
):
    if not simulate_plc:
        simulate_plc = False

    simulator_pod = get_kubectl_workload_items(
        prefixes="opcplc-00000", service_type="pod", namespace=namespace
    )
    assert bool(simulator_pod) is simulate_plc
