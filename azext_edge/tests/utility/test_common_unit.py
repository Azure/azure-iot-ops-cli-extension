# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import string
from os import environ
from typing import List, Tuple

import pytest

from azext_edge.edge.util import (
    is_enabled_str,
    is_env_flag_enabled,
    parse_dot_notation,
    parse_kvp_nargs,
    upsert_by_discriminator,
    url_safe_random_chars,
)

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


@pytest.mark.parametrize(
    "input_data,expected",
    [
        ([], {}),
        (None, {}),
        (["a="], {"a": ""}),
        (["a=", "b="], {"a": "", "b": ""}),
        (["a"], {"a": None}),
        (["a", "b"], {"a": None, "b": None}),
        (["a=b"], {"a": "b"}),
        (["a=b", "c=d", "123=456"], {"a": "b", "c": "d", "123": "456"}),
    ],
)
def test_parse_kvp_nargs(input_data: List[str], expected: dict):
    result = parse_kvp_nargs(input_data)
    assert result == expected


@pytest.mark.parametrize(
    "input_data,expected",
    [
        (["a.b.c=value"], {"a": {"b": {"c": "value"}}}),
        (["a.b.c=value1", "a.b.d=value2"], {"a": {"b": {"c": "value1", "d": "value2"}}}),
        (["x.y=value3"], {"x": {"y": "value3"}}),
        (["a.b=value1", "a.c=value2"], {"a": {"b": "value1", "c": "value2"}}),
        (
            ["user.name.first=John", "user.name.last=Doe", "user.age=30"],
            {"user": {"name": {"first": "John", "last": "Doe"}, "age": "30"}},
        ),
        (["a.b.c=value", "a.b=value2"], {"a": {"b": "value2"}}),
        (["a=value", "a.b=value2"], {"a": {"b": "value2"}}),
        (["a.b.c"], {}),
        (["a.b=CN = Contoso Intermediate CA"], {"a": {"b": "CN = Contoso Intermediate CA"}}),
        (["a.b = some value "], {"a": {"b": "some value"}}),
    ],
)
def test_parse_dot_notation(input_data: List[str], expected: dict):
    assert parse_dot_notation(input_data) == expected


@pytest.mark.parametrize(
    "initial, new_config, disc_key, expected",
    [
        (
            [{"discriminator": "a", "value": 1}, {"discriminator": "b", "value": 2}],
            {"discriminator": "b", "value": 99},
            "discriminator",
            [{"discriminator": "a", "value": 1}, {"discriminator": "b", "value": 99}],
        ),
        (
            [{"discriminator": "a", "value": 1}],
            {"discriminator": "c", "value": 3},
            "discriminator",
            [{"discriminator": "a", "value": 1}, {"discriminator": "c", "value": 3}],
        ),
        (
            [{"type": "x", "data": 1}, {"type": "y", "data": 2}],
            {"type": "y", "data": 22},
            "type",
            [{"type": "x", "data": 1}, {"type": "y", "data": 22}],
        ),
        (
            [{"type": "x", "data": 1}],
            {"type": "z", "data": 3},
            "type",
            [{"type": "x", "data": 1}, {"type": "z", "data": 3}],
        ),
        ([], {"discriminator": "a", "value": 1}, "discriminator", [{"discriminator": "a", "value": 1}]),
    ],
)
def test_upsert_by_discriminator(initial, disc_key, new_config, expected):
    result = upsert_by_discriminator(initial=initial, disc_key=disc_key, config=new_config)
    assert result == expected
