# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from time import sleep
from typing import Optional
from ....helpers import run

# args to wait for --simulate-plc
MAX_TRIES = 10
SLEEP_INTERVAL = 60


def assert_simulate_plc_args(
    custom_location: str,
    simulate_plc: Optional[bool] = None,
    **_
):
    if not simulate_plc:
        simulate_plc = False
    # note that the simulator may take a bit
    query_result = run(f"az iot ops asset query --cl {custom_location}")
    tries = 0
    while simulate_plc and not query_result and tries < MAX_TRIES:
        sleep(SLEEP_INTERVAL)
        query_result = run(f"az iot ops asset query --cl {custom_location}")
        tries += 1
    assert bool(query_result) is simulate_plc

    query_result = run(f"az iot ops asset endpoint query --cl {custom_location}")
    assert bool(query_result) is simulate_plc
