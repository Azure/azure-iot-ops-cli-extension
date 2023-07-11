# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# PRIVATE DISTRIBUTION FOR NDA CUSTOMERS ONLY
# --------------------------------------------------------------------------------------------

import pytest
from pathlib import PurePath
from io import BufferedReader


@pytest.fixture
def stub_raw_stats() -> BufferedReader:
    with open(PurePath(PurePath(__file__).parent, "raw_stats.txt"), mode="rb", encoding=None) as f:
        yield f
