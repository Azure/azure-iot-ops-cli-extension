# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest
from azext_edge.edge.providers.base import load_config_context
from ...generators import generate_generic_id

context_name = generate_generic_id()


@pytest.mark.parametrize("mocked_config", [{"namespace": context_name}, {}], indirect=True)
def test_load_config_context(mocked_config: dict):
    load_config_context(context_name=context_name)
    from azext_edge.edge.providers.base import DEFAULT_NAMESPACE

    if mocked_config["param"]:
        assert DEFAULT_NAMESPACE == context_name
    else:
        assert DEFAULT_NAMESPACE == "azure-iot-operations"
