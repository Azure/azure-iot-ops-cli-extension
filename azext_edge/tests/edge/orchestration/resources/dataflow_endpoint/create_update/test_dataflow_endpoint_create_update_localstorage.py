# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azext_edge.edge.commands_dataflow import create_dataflow_endpoint_localstorage
from ..helper import assert_dataflow_endpoint_create_update


@pytest.mark.parametrize(
    "params, expected_payload",
    [
        (
            {
                "pvc_reference": "mypvc",
            },
            {
                "endpointType": "LocalStorage",
                "localStorageSettings": {
                    "persistentVolumeClaimRef": "mypvc",
                },
            },
        ),
    ]
)
def test_dataflow_endpoint_create_localstorage(
    mocked_cmd,
    params: dict,
    expected_payload: dict,
    mocked_responses: Mock,
):
    assert_dataflow_endpoint_create_update(
        mocked_responses=mocked_responses,
        expected_payload=expected_payload,
        mocked_cmd=mocked_cmd,
        params=params,
        dataflow_endpoint_func=create_dataflow_endpoint_localstorage,
    )
