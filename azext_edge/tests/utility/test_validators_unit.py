# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------


from types import SimpleNamespace

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_edge.edge._validators import validate_namespace


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
