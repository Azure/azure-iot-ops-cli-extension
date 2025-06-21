# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from random import randint
from typing import Optional
import responses
from azext_edge.edge.commands_namespaces import (
    add_namespace_custom_asset_dataset,
    add_namespace_opcua_asset_dataset,
    list_namespace_asset_datasets,
    remove_namespace_asset_dataset,
    show_namespace_asset_dataset,
    update_namespace_custom_asset_dataset,
    update_namespace_opcua_asset_dataset,
    add_namespace_custom_asset_dataset_point,
    add_namespace_opcua_asset_dataset_point,
    list_namespace_asset_dataset_points,
    remove_namespace_asset_dataset_point
)

from .test_namespace_assets_unit import (
    get_namespace_asset_mgmt_uri, get_namespace_asset_record, add_device_get_call
)
from ....generators import generate_random_string


def generate_dataset(dataset_name: Optional[str] = None, num_data_points: int = 0) -> dict:
    """Generates a dataset with the given name and number of data points."""
    dataset_name = dataset_name or generate_random_string()
    return {
        "name": dataset_name,
        "dataSource": f"nsu=http://microsoft.com/Opc/OpcPlc/Oven;i={randint(1, 1000)}",
        "typeRef": "datasetTypeRef",
        "datasetCOnfiguration": json.dumps({
            "publishingInterval": randint(1, 10),
            "samplingInterval": randint(1, 10),
            "queueSize": randint(1, 10)
        }),
        "destinations": [
            {
                "target": "Mqtt",
                "configuration": {
                    "topic": f"/contoso/{generate_random_string()}",
                    "retain": "Never",
                    "qos": "Qos1",
                    "ttl": randint(1, 60)
                }
            }
        ],
        "dataPoints": [
            {
                "name": f"{dataset_name}DataPoint{i + 1}",
                "dataSource": f"nsu=subtest;s=FastUInt{i + 1}",
                "dataPointConfiguration": json.dumps(
                    {
                        "publishingInterval": randint(1, 10),
                        "samplingInterval": randint(1, 10),
                        "queueSize": randint(1, 10)
                    }
                )
            }for i in range(num_data_points)
        ]
    }


def test_add_namespace_asset_dataset(mocked_cmd, mocked_responses: responses):
    pass


def test_list_namespace_asset_datasets(mocked_cmd, mocked_responses: responses):
    pass


def test_remove_namespace_asset_dataset(mocked_cmd, mocked_responses: responses):
    pass


def test_show_namespace_asset_dataset(mocked_cmd, mocked_responses: responses):
    pass


def test_update_namespace_asset_dataset(mocked_cmd, mocked_responses: responses):
    pass


def test_add_namespace_asset_dataset_point(mocked_cmd, mocked_responses: responses):
    pass


def test_list_namespace_asset_dataset_points(mocked_cmd, mocked_responses: responses):
    pass


def test_remove_namespace_asset_dataset_point(mocked_cmd, mocked_responses: responses):
    pass
