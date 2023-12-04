# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from .....generators import generate_generic_id

context_name = generate_generic_id()


@pytest.mark.parametrize("mocked_resource_management_client", [
    {"resource_groups.get": {"location": generate_generic_id()}},
], ids=["extended_location"], indirect=True)
def test_get_location(mocked_cmd, mocked_resource_management_client):
    from azext_edge.edge.providers.rpsaas.base_provider import RPSaaSBaseProvider
    resource_group_name = generate_generic_id()
    provider = RPSaaSBaseProvider(
        mocked_cmd,
        generate_generic_id(),
        generate_generic_id()
    )
    result = provider.get_location(resource_group_name)

    mocked_resource_management_client.resource_groups.get.assert_called_once()
    kwargs = mocked_resource_management_client.resource_groups.get.call_args.kwargs
    assert kwargs["resource_group_name"] == resource_group_name

    rg_call = mocked_resource_management_client.resource_groups.get.return_value.as_dict.return_value
    assert result == rg_call["location"]
