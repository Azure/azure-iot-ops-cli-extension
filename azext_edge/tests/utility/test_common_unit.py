# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import string
from os import environ
from typing import Tuple

import pytest

from azext_edge.edge.util import is_env_flag_enabled, url_safe_random_chars, is_enabled_str

from ..generators import generate_random_string


@pytest.mark.parametrize("expected_count", [10, 5, 0, -1])
def test_url_safe_random_chars(expected_count: int):
    result = url_safe_random_chars(expected_count)
    expected_count = max(expected_count, 0)
    assert len(result) == expected_count

    expected_char_set = string.ascii_lowercase + string.ascii_uppercase + string.digits
    for c in result:
        assert c in expected_char_set


@pytest.mark.parametrize(
    "env_value_pair",
    [
        ("true", True),
        ("True", True),
        ("y", True),
        ("1", True),
        ("False", False),
        ("false", False),
        ("0", False),
        ("no", False),
        ("random", False),
        ("", False),
    ],
)
@pytest.mark.parametrize("flag_key", [generate_random_string()])
def test_is_env_flag_enabled(env_value_pair: Tuple[str, bool], flag_key: str):
    environ[flag_key] = env_value_pair[0]

    is_enabled = is_env_flag_enabled(flag_key)
    assert is_enabled is env_value_pair[1]
    del environ[flag_key]


@pytest.mark.parametrize(
    "input_pair", [("Enabled", True), ("enabled", True), ("Disabled", False), ("disabled", False), (None, False)]
)
def test_is_enabled(input_pair: Tuple[str, bool]):
    is_enabled = is_enabled_str(input_pair[0])

    assert is_enabled is input_pair[1]
