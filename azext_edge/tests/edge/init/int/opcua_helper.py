# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional
from ....helpers import run


def assert_simulate_plc_args(
    custom_location: str,
    simulate_plc: Optional[bool] = None,
    **_
):
    if not simulate_plc:
        simulate_plc = False
    # note that the simulator may take a bit
    query_result = run(f"az iot ops asset query --cl {custom_location}")
    assert bool(query_result) is simulate_plc
    query_result = run(f"az iot ops asset endpoint query --cl {custom_location}")
    assert bool(query_result) is simulate_plc
