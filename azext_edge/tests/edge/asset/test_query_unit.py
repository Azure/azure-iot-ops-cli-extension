# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import ResourceTypeMapping
from azext_edge.edge.commands_assets import query_assets

from .conftest import ASSETS_PATH
from ...generators import generate_generic_id


@pytest.mark.parametrize("mocked_build_query", [{
    "path": ASSETS_PATH,
    "result": [{"result": generate_generic_id()}]
}], ids=["query"], indirect=True)
@pytest.mark.parametrize("req", [
    {},
    {
        "asset_type": generate_generic_id(),
        "custom_location_name": generate_generic_id(),
        "description": generate_generic_id(),
        "disabled": True,
        "display_name": generate_generic_id(),
        "documentation_uri": generate_generic_id(),
        "endpoint": generate_generic_id(),
        "external_asset_id": generate_generic_id(),
        "hardware_revision": generate_generic_id(),
        "location": generate_generic_id(),
        "manufacturer": generate_generic_id(),
        "manufacturer_uri": generate_generic_id(),
        "model": generate_generic_id(),
        "product_code": generate_generic_id(),
        "serial_number": generate_generic_id(),
        "software_revision": generate_generic_id(),
        "resource_group_name": generate_generic_id(),
    },
    {
        "asset_type": generate_generic_id(),
        "disabled": False,
        "resource_group_name": generate_generic_id(),
    },
])
def test_query_assets(mocked_cmd, mocked_get_subscription_id, mocked_build_query, req):
    result = query_assets(
        cmd=mocked_cmd,
        **req
    )
    assert result == mocked_build_query.return_value
    query_args = mocked_build_query.call_args.kwargs
    assert query_args["subscription_id"] == mocked_get_subscription_id.return_value
    assert query_args["location"] == req.get("location")
    assert query_args["resource_group"] == req.get("resource_group_name")
    assert query_args["type"] == ResourceTypeMapping.asset.value
    assert query_args["additional_project"] == "extendedLocation"

    expected_query = ""
    if req.get("asset_type"):
        expected_query += f"| where properties.assetType =~ \"{req['asset_type']}\""
    if req.get("custom_location_name"):  # ##
        expected_query += f"| where extendedLocation.name contains \"{req['custom_location_name']}\""
    if req.get("description"):
        expected_query += f"| where properties.description =~ \"{req['description']}\""
    if req.get("display_name"):
        expected_query += f"| where properties.displayName =~ \"{req['display_name']}\""
    if req.get("disabled"):
        expected_query += f"| where properties.enabled == {not req['disabled']}"
    if req.get("documentation_uri"):
        expected_query += f"| where properties.documentationUri =~ \"{req['documentation_uri']}\""
    if req.get("endpoint"):
        expected_query += f"| where properties.assetEndpointProfileUri =~ \"{req['endpoint']}\""
    if req.get("external_asset_id"):
        expected_query += f"| where properties.externalAssetId =~ \"{req['external_asset_id']}\""
    if req.get("hardware_revision"):
        expected_query += f"| where properties.hardwareRevision =~ \"{req['hardware_revision']}\""
    if req.get("manufacturer"):
        expected_query += f"| where properties.manufacturer =~ \"{req['manufacturer']}\""
    if req.get("manufacturer_uri"):
        expected_query += f"| where properties.manufacturerUri =~ \"{req['manufacturer_uri']}\""
    if req.get("model"):
        expected_query += f"| where properties.model =~ \"{req['model']}\""
    if req.get("product_code"):
        expected_query += f"| where properties.productCode =~ \"{req['product_code']}\""
    if req.get("serial_number"):
        expected_query += f"| where properties.serialNumber =~ \"{req['serial_number']}\""
    if req.get("software_revision"):
        expected_query += f"| where properties.softwareRevision =~ \"{req['software_revision']}\""
    assert query_args["custom_query"] == expected_query
