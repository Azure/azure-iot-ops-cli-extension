# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
import string
from azext_edge.edge.util import url_safe_random_chars


@pytest.mark.parametrize("expected_count", [10, 5, 0, -1])
def test_url_safe_random_chars(expected_count: int):
    result = url_safe_random_chars(expected_count)
    if expected_count < 0:
        expected_count = 0
    assert len(result) == expected_count

    expected_char_set = string.ascii_lowercase + string.ascii_uppercase + string.digits
    for c in result:
        assert c in expected_char_set
