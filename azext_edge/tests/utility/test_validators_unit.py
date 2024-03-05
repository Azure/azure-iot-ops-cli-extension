# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


from types import SimpleNamespace

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge._validators import validate_namespace, validate_resource_name


@pytest.mark.parametrize(
    "namespace",
    [
        "valid-namespace-1",
        "an0th3r-val1d-n4m3sp4c3",
        "a",
        "this-string-has-63-characters--so-this-is-a-63-character-string",
    ],
)
def test_namespace_validator(namespace):
    validate_namespace(SimpleNamespace(namespace=namespace))


@pytest.mark.parametrize(
    "namespace",
    [
        "edge\\" "invalid.namespace",
        "bad namespace",
        "another_bad_namespace",
        "CAPS ARE ALSO NOT ALLOWED",
        "this-would-be-a-valid-namespace-except-for-some-extra-characters",
    ],
)
def test_namespace_validator_errors(namespace):
    with pytest.raises(InvalidArgumentValueError):
        validate_namespace(SimpleNamespace(namespace=namespace))


@pytest.mark.parametrize(
    "resource_name",
    [
        "valid-resource-name-1",
        "an0th3r-val1d-r3s0urc3-n4m3",
        "valid-resource-name-*",
        "valid-resource-name-?",
        "Valid-Resource-Name",
        "1234455666333",
    ],
)
def test_resource_name_validator_none(resource_name):
    validate_resource_name(SimpleNamespace(resource_name=resource_name))


@pytest.mark.parametrize(
    "resource_name",
    [
        "invalid*resource*name[]",
        "invalid?resource?name@#$%^^",
        "invalid-resource-name-!",
        "invalid-resource-name-.",
        "invalid-resource-name-/",
    ],
)
def test_resource_name_validator_errors(resource_name):
    with pytest.raises(InvalidArgumentValueError):
        validate_resource_name(SimpleNamespace(resource_name=resource_name))
