# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
from pathlib import PurePath
from io import BufferedReader


@pytest.fixture
def stub_raw_stats() -> BufferedReader:
    with open(PurePath(PurePath(__file__).parent, "raw_stats.txt"), mode="rb", encoding=None) as f:
        yield f
