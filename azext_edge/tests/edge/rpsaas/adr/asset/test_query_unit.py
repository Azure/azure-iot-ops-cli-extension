# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.commands_assets import query_assets

from .conftest import ASSETS_PATH
from .....generators import generate_random_string


@pytest.mark.parametrize("mocked_build_query", [{
    "path": ASSETS_PATH,
    "result": [{"result": generate_random_string()}]
}], ids=["query"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "asset_type": generate_random_string(),
        "custom_location_name": generate_random_string(),
        "description": generate_random_string(),
        "disabled": True,
        "display_name": generate_random_string(),
        "documentation_uri": generate_random_string(),
        "endpoint": generate_random_string(),
        "external_asset_id": generate_random_string(),
        "hardware_revision": generate_random_string(),
        "location": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturer_uri": generate_random_string(),
        "model": generate_random_string(),
        "product_code": generate_random_string(),
        "serial_number": generate_random_string(),
        "software_revision": generate_random_string(),
        "resource_group_name": generate_random_string(),
    },
    {
        "asset_type": generate_random_string(),
        "disabled": False,
        "resource_group_name": generate_random_string(),
    },
])
def test_query_assets(mocked_cmd, mocked_get_subscription_id, mocked_responses, req):
    result = query_assets(
        cmd=mocked_cmd,
        **req
    )
    assert result == mocked_build_query.return_value
    query_args = mocked_build_query.call_args.kwargs
    assert query_args["subscription_id"] == mocked_get_subscription_id.return_value
    assert query_args["location"] == req.get("location")
    assert query_args["resource_group"] == req.get("resource_group_name")
    assert query_args["type"] == ResourceTypeMapping.asset.full_resource_path
    assert query_args["additional_project"] == "extendedLocation"

    expected_query = []
    if req.get("asset_type"):
        expected_query.append(f" where properties.assetType =~ \"{req['asset_type']}\"")
    if req.get("custom_location_name"):
        expected_query.append(f" where extendedLocation.name contains \"{req['custom_location_name']}\"")
    if req.get("description"):
        expected_query.append(f" where properties.description =~ \"{req['description']}\"")
    if req.get("display_name"):
        expected_query.append(f" where properties.displayName =~ \"{req['display_name']}\"")
    if req.get("disabled"):
        expected_query.append(f" where properties.enabled == {not req['disabled']}")
    if req.get("documentation_uri"):
        expected_query.append(f" where properties.documentationUri =~ \"{req['documentation_uri']}\"")
    if req.get("endpoint"):
        expected_query.append(f" where properties.assetEndpointProfileUri =~ \"{req['endpoint']}\"")
    if req.get("external_asset_id"):
        expected_query.append(f" where properties.externalAssetId =~ \"{req['external_asset_id']}\"")
    if req.get("hardware_revision"):
        expected_query.append(f" where properties.hardwareRevision =~ \"{req['hardware_revision']}\"")
    if req.get("manufacturer"):
        expected_query.append(f" where properties.manufacturer =~ \"{req['manufacturer']}\"")
    if req.get("manufacturer_uri"):
        expected_query.append(f" where properties.manufacturerUri =~ \"{req['manufacturer_uri']}\"")
    if req.get("model"):
        expected_query.append(f" where properties.model =~ \"{req['model']}\"")
    if req.get("product_code"):
        expected_query.append(f" where properties.productCode =~ \"{req['product_code']}\"")
    if req.get("serial_number"):
        expected_query.append(f" where properties.serialNumber =~ \"{req['serial_number']}\"")
    if req.get("software_revision"):
        expected_query.append(f" where properties.softwareRevision =~ \"{req['software_revision']}\"")

    custom_query = query_args["custom_query"].split("|")[1:]

    assert len(custom_query) == len(expected_query)
    for i in expected_query:
        assert i in custom_query
