# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from .....generators import generate_generic_id

context_name = generate_generic_id()


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resources.begin_delete": {"result": generate_generic_id()}},
], ids=["result"], indirect=True)
def test_delete(mocked_cmd, mocked_resource_management_client):
    from azext_edge.edge.providers.rpsaas.base_provider import RPSaaSBaseProvider
    api_version = generate_generic_id()
    resource_type = generate_generic_id()
    resource_name = generate_generic_id()
    resource_group_name = generate_generic_id()
    provider = RPSaaSBaseProvider(
        mocked_cmd,
        api_version,
        resource_type
    )
    result = provider.delete(resource_name, resource_group_name)

    mocked_resource_management_client.resources.begin_delete.assert_called_once()
    kwargs = mocked_resource_management_client.resources.begin_delete.call_args.kwargs
    assert kwargs["resource_group_name"] == resource_group_name
    assert kwargs["resource_provider_namespace"] == resource_type
    assert kwargs["parent_resource_path"] == ""
    assert kwargs["resource_type"] == ""
    assert kwargs["resource_name"] == resource_name
    assert kwargs["api_version"] == api_version
    assert result is None
