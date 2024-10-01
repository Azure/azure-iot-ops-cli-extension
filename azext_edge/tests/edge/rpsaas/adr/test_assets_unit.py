# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Dict, Optional
import json
import pytest
import responses

from azure.cli.core.azclierror import InvalidArgumentValueError
from azext_edge.edge.commands_assets import (
    create_asset,
    delete_asset,
    list_assets,
    show_asset,
    update_asset,
    list_asset_datasets,
    show_asset_dataset,
    add_asset_data_point,
    export_asset_data_points,
    import_asset_events,
    list_asset_data_points,
    remove_asset_data_point,
    add_asset_event,
    export_asset_events,
    import_asset_data_points,
    list_asset_events,
    remove_asset_event,
)
from azext_edge.edge.common import FileType

from .conftest import get_asset_mgmt_uri, get_asset_record
from ....generators import generate_random_string


@pytest.mark.parametrize("req", [
    {},
    {
        "custom_attributes": [generate_random_string()],
        "description": generate_random_string(),
        "display_name": generate_random_string(),
        "disabled": True,
        "documentation_uri": generate_random_string(),
        "events": generate_random_string(),
        "events_file_path": generate_random_string(),
        "external_asset_id": generate_random_string(),
        "hardware_revision": generate_random_string(),
        "instance_resource_group": generate_random_string(),
        "instance_subscription": generate_random_string(),
        "location": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturer_uri": generate_random_string(),
        "model": generate_random_string(),
        "product_code": generate_random_string(),
        "serial_number": generate_random_string(),
        "software_revision": generate_random_string(),
        "ds_publishing_interval": 3333,
        "ds_sampling_interval": 44,
        "ds_queue_size": 55,
        "ev_publishing_interval": 666,
        "ev_sampling_interval": 777,
        "ev_queue_size": 888,
        "tags": generate_random_string(),
    },
    {
        "instance_resource_group": generate_random_string(),
        "disabled": False,
        "events": generate_random_string(),
        "ds_publishing_interval": 3333,
        "ds_sampling_interval": 44,
        "ev_queue_size": 888,
    }
])
def test_asset_create(
    mocked_cmd,
    asset_helpers_fixture,
    mocked_get_extended_location,
    mocked_responses: responses,
    req: Dict[str, str]
):
    asset_name = generate_random_string()
    endpoint_profile = generate_random_string()
    resource_group_name = generate_random_string()
    instance_name = generate_random_string()

    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    result = create_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        endpoint_profile=endpoint_profile,
        resource_group_name=resource_group_name,
        instance_name=instance_name,
        wait_sec=0,
        **req
    )
    assert result == mock_asset_record
    call_body = json.loads(mocked_responses.calls[0].request.body)
    extended_location = mocked_get_extended_location.original_return_value
    assert call_body["extendedLocation"]["name"] == extended_location["name"]
    assert call_body["location"] == req.get("location", extended_location["cluster_location"])
    assert call_body["tags"] == req.get("tags")

    call_body_props = call_body["properties"]
    assert call_body_props["assetEndpointProfileRef"] == endpoint_profile

    patched_up = asset_helpers_fixture["update_properties"]
    req["disabled"] = req.get("disabled", False)
    req["ds_publishing_interval"] = req.get("ds_publishing_interval", 1000)
    req["ds_sampling_interval"] = req.get("ds_sampling_interval", 500)
    req["ds_queue_size"] = req.get("ds_queue_size", 1)
    req["ev_publishing_interval"] = req.get("ev_publishing_interval", 1000)
    req["ev_sampling_interval"] = req.get("ev_sampling_interval", 500)
    req["ev_queue_size"] = req.get("ev_queue_size", 1)
    assert call_body_props.get("defaultDataPointsConfiguration") is None
    assert call_body_props.get("defaultEventsConfiguration") is None
    for arg in patched_up.call_args.kwargs:
        assert patched_up.call_args.kwargs[arg] == req.get(arg)
        assert call_body_props.get(arg) is None

    mocked_get_extended_location.assert_called_with(
        cmd=mocked_cmd,
        instance_name=instance_name,
        instance_resource_group=req.get("instance_resource_group", resource_group_name),
        instance_subscription=req.get("instance_subscription")
    )
    assert asset_helpers_fixture["process_asset_sub_points_file_path"].called is bool(req.get("events_file_path"))


@pytest.mark.parametrize("discovered", [False])  # TODO: discovered
def test_asset_delete(mocked_cmd, mocked_check_cluster_connectivity, mocked_responses: responses, discovered: bool):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name, discovered=discovered
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json="" if discovered else mock_asset_record,
        status=404 if discovered else 200,
        content_type="application/json",
    )
    if discovered:
        mocked_responses.add(
            method=responses.GET,
            url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name, discovered=True),
            json=mock_asset_record,
            status=200,
            content_type="application/json",
        )
    mocked_responses.add(
        method=responses.DELETE,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name, discovered=discovered),
        status=202,
        content_type="application/json",
    )

    delete_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        wait_sec=0,
    )
    assert len(mocked_responses.calls) == (3 if discovered else 2)


@pytest.mark.parametrize("records", [0, 2])
@pytest.mark.parametrize("resource_group_name", [None, generate_random_string()])
def test_asset_list(
    mocked_cmd, mocked_responses: responses, records: int, resource_group_name: Optional[str]
):
    mock_asset_records = {
        "value": [
            get_asset_record(
                asset_name=generate_random_string(),
                asset_resource_group=resource_group_name,
                discovered=False  # TODO: discovered
            )
            for _ in range(records)
        ]
    }

    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(
            asset_name="", asset_resource_group=resource_group_name, discovered=False
        ),
        json=mock_asset_records,
        status=200,
        content_type="application/json",
    )

    result = list(list_assets(cmd=mocked_cmd, resource_group_name=resource_group_name))
    assert result == mock_asset_records["value"]
    assert len(mocked_responses.calls) == 1


@pytest.mark.parametrize("discovered", [False])  # TODO: discovered
def test_asset_show(mocked_cmd, mocked_responses: responses, discovered: bool):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()

    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name, discovered=discovered
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json="" if discovered else mock_asset_record,
        status=404 if discovered else 200,
        content_type="application/json",
    )
    if discovered:
        mocked_responses.add(
            method=responses.GET,
            url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name, discovered=True),
            json=mock_asset_record,
            status=200,
            content_type="application/json",
        )

    result = show_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
    )
    assert result == mock_asset_record
    assert len(mocked_responses.calls) == (2 if discovered else 1)


@pytest.mark.parametrize("req", [
    {},
    {
        "custom_attributes": [generate_random_string()],
        "description": generate_random_string(),
        "disabled": True,
        "display_name": generate_random_string(),
        "documentation_uri": generate_random_string(),
        "hardware_revision": generate_random_string(),
        "manufacturer": generate_random_string(),
        "manufacturer_uri": generate_random_string(),
        "model": generate_random_string(),
        "product_code": generate_random_string(),
        "serial_number": generate_random_string(),
        "software_revision": generate_random_string(),
        "ds_publishing_interval": 3333,
        "ds_sampling_interval": 44,
        "ds_queue_size": 55,
        "ev_publishing_interval": 666,
        "ev_sampling_interval": 777,
        "ev_queue_size": 888,
        "tags": generate_random_string(),
    },
    {
        "custom_attributes": [generate_random_string()],
        "disabled": False,
        "ds_publishing_interval": 3333,
        "ds_sampling_interval": 44,
        "ev_queue_size": 888,
    },
])
def test_asset_update(
    mocked_cmd,
    asset_helpers_fixture,
    mocked_check_cluster_connectivity,
    mocked_responses: responses,
    req: dict
):
    # use non discovered since delete shows the update_ops is selected correctly
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()

    # make sure that the get vs patch have different results
    mock_original_asset = get_asset_record(asset_name=asset_name, asset_resource_group=resource_group_name)
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name, full=True
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_original_asset,
        status=200,
        content_type="application/json",
    )
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    result = update_asset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        wait_sec=0,
        **req
    )
    assert result == mock_asset_record
    assert len(mocked_responses.calls) == 2
    call_body = json.loads(mocked_responses.calls[-1].request.body)
    assert call_body.get("tags") == req.get("tags", mock_original_asset.get("tags"))

    call_body_props = call_body["properties"]
    patched_up = asset_helpers_fixture["update_properties"]
    assert call_body_props.get("defaultDataPointsConfiguration") is None
    assert call_body_props.get("defaultEventsConfiguration") is None
    for arg in patched_up.call_args.kwargs:
        assert patched_up.call_args.kwargs[arg] == req.get(arg)
        assert call_body_props.get(arg) is None


# Dataset
@pytest.mark.parametrize("full", [True, False])
def test_dataset_list(
    mocked_cmd,
    mocked_responses: responses,
    full: bool
):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name, full=full
    )
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    result = list_asset_datasets(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )
    assert result == mock_asset_record["properties"].get("datasets", [])


def test_dataset_show(
    mocked_cmd,
    mocked_responses: responses,
):
    dataset_name = generate_random_string()
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name, full=True
    )
    dataset = {
        "name": dataset_name,
        "dataPoints": [{generate_random_string(): generate_random_string()}]
    }
    mock_asset_record["properties"]["datasets"].append(dataset)
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    result = show_asset_dataset(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        dataset_name=dataset_name
    )
    assert result == dataset


# Dataset Data Points
@pytest.mark.parametrize("dataset_present", [True, False])
@pytest.mark.parametrize("observability_mode", [None, "log"])
@pytest.mark.parametrize("queue_size", [True, 2])
@pytest.mark.parametrize("sampling_interval", [True, 1000])
@pytest.mark.parametrize("replace", [False, True])
def test_data_point_add(
    mocked_cmd,
    mocked_responses: responses,
    mocked_check_cluster_connectivity,
    dataset_present,
    observability_mode,
    queue_size,
    sampling_interval,
    replace
):
    dataset_name = "default"
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    data_point_name = generate_random_string()
    data_source = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    if dataset_present:
        dataset = {
            "name": dataset_name,
            "dataPoints": [
                {"name": generate_random_string(), generate_random_string(): generate_random_string()}
            ]
        }
        if replace:
            dataset["dataPoints"].append({
                "name": data_point_name, generate_random_string(): generate_random_string()
            })
        mock_asset_record["properties"]["datasets"] = [dataset]
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    result_datapoints = [{generate_random_string(): generate_random_string()}]
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json={"properties": {"datasets": [{
            "name": dataset_name,
            "dataPoints": result_datapoints
        }]}},
        status=200,
        content_type="application/json",
    )
    result = add_asset_data_point(
        cmd=mocked_cmd,
        dataset_name=dataset_name,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        data_point_name=data_point_name,
        data_source=data_source,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        replace=replace,
        wait_sec=0,
    )
    assert result == result_datapoints
    datasets = json.loads(mocked_responses.calls[-1].request.body)["properties"]["datasets"]
    assert datasets
    point = datasets[0]["dataPoints"][-1]
    assert point["name"] == data_point_name
    assert point["dataSource"] == data_source
    assert point["observabilityMode"] == (observability_mode or "none").capitalize()
    custom_config = json.loads(point["dataPointConfiguration"])
    assert custom_config.get("queueSize") == queue_size
    assert custom_config.get("samplingInterval") == sampling_interval


def test_data_point_add_error(
    mocked_cmd,
    mocked_responses: responses,
    mocked_check_cluster_connectivity,
):
    dataset_name = "default"
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    data_point_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    dataset = {
        "name": dataset_name,
        "dataPoints": [
            {"name": data_point_name, generate_random_string(): generate_random_string()},
            {"name": generate_random_string(), generate_random_string(): generate_random_string()}
        ]
    }
    mock_asset_record["properties"]["datasets"] = [dataset]
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    with pytest.raises(InvalidArgumentValueError):
        add_asset_data_point(
            cmd=mocked_cmd,
            dataset_name=dataset_name,
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            data_point_name=data_point_name,
            data_source=generate_random_string(),
            wait_sec=0,
        )


@pytest.mark.parametrize("data_points_present", [True, False])
@pytest.mark.parametrize("extension", FileType.list())
@pytest.mark.parametrize("output_dir", [None, generate_random_string()])
@pytest.mark.parametrize("replace", [False, True])
def test_data_point_export(
    mocked_cmd,
    mocked_responses: responses,
    mocked_dump_content_to_file,
    data_points_present,
    extension,
    output_dir,
    replace,
):
    dataset_name = "default"
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    dataset = {"name": dataset_name}
    if data_points_present:
        dataset["dataPoints"] = [
            {
                "dataPointConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
                "dataSource": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            },
            {
                "dataPointConfiguration": "{}",
                "name": generate_random_string(),
                "dataSource": generate_random_string(),
            },
            {
                "dataPointConfiguration": "{\"samplingInterval\": 100}",
                "dataSource": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            }
        ]
    mock_asset_record["properties"]["datasets"] = [dataset]

    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    result = export_asset_data_points(
        cmd=mocked_cmd,
        dataset_name=dataset_name,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        extension=extension,
        output_dir=output_dir,
        replace=replace
    )
    assert result["file_path"] == mocked_dump_content_to_file.return_value

    default_config = mock_asset_record["properties"].get("defaultDatasetsConfiguration", "{}")
    expected_fieldnames = None
    if extension in [FileType.csv.value]:
        from azext_edge.edge.providers.rpsaas.adr.assets import _convert_sub_points_to_csv
        expected_fieldnames = _convert_sub_points_to_csv(
            sub_points=dataset.get("dataPoints", []),
            sub_point_type="dataPoints",
            default_configuration=default_config,
            portal_friendly=True
        )

    call_kwargs = mocked_dump_content_to_file.call_args.kwargs
    assert call_kwargs["content"] == dataset.get("dataPoints", [])
    assert call_kwargs["file_name"] == f"{asset_name}_{dataset_name}_datapoints"
    assert call_kwargs["extension"] == extension.replace("-", ".")
    assert call_kwargs["fieldnames"] == expected_fieldnames
    assert call_kwargs["output_dir"] == output_dir
    assert call_kwargs["replace"] == replace


@pytest.mark.parametrize("replace", [False, True])
def test_data_point_import(
    mocker,
    mocked_cmd,
    mocked_responses: responses,
    mocked_check_cluster_connectivity,
    mocked_deserialize_file_content,
    replace
):
    # remove logger warnings
    mocker.patch("azext_edge.edge.providers.rpsaas.adr.assets.logger")
    dataset_name = "default"
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    dup_name = generate_random_string()
    file_path = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    file_dataset = {
        "name": dataset_name,
        "dataPoints": [
            {
                "dataPointConfiguration": "{\"samplingInterval\": 300, \"queueSize\": 30}",
                "dataSource": generate_random_string(),
                "name": dup_name,
                "observabilityMode": generate_random_string()
            },
            {
                "dataPointConfiguration": "{\"samplingInterval\": 100}",
                "dataSource": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            }
        ]
    }
    cloud_dataset = {
        "name": dataset_name,
        "dataPoints": [
            {
                "dataPointConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
                "dataSource": generate_random_string(),
                "name": dup_name,
                "observabilityMode": generate_random_string()
            },
            {
                "dataPointConfiguration": "{}",
                "name": generate_random_string(),
                "dataSource": generate_random_string(),
            }
        ]
    }
    mocked_deserialize_file_content.return_value = file_dataset["dataPoints"]
    mock_asset_record["properties"]["datasets"] = [cloud_dataset]
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    result_datapoints = [{generate_random_string(): generate_random_string()}]
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json={"properties": {"datasets": [{
            "name": dataset_name,
            "dataPoints": result_datapoints
        }]}},
        status=200,
        content_type="application/json",
    )
    result = import_asset_data_points(
        cmd=mocked_cmd,
        asset_name=asset_name,
        dataset_name=dataset_name,
        resource_group_name=resource_group_name,
        file_path=file_path,
        replace=replace,
        wait_sec=0,
    )

    assert result == result_datapoints
    mocked_deserialize_file_content.assert_called_once_with(file_path=file_path)
    datasets = json.loads(mocked_responses.calls[-1].request.body)["properties"]["datasets"]
    assert datasets
    point_map = {point["name"]: point for point in datasets[0]["dataPoints"]}
    assert file_dataset["dataPoints"][1]["name"] in point_map
    assert dup_name in point_map
    # check the duplicate point
    if replace:
        point = file_dataset["dataPoints"][0]
        assert file_dataset["dataPoints"][1]["name"] in point_map
    else:
        point = cloud_dataset["dataPoints"][0]
    assert cloud_dataset["dataPoints"][1]["name"] in point_map
    assert point_map[dup_name]["dataPointConfiguration"] == point["dataPointConfiguration"]
    assert point_map[dup_name]["dataSource"] == point["dataSource"]
    assert point_map[dup_name]["observabilityMode"] == point["observabilityMode"]


@pytest.mark.parametrize("data_points_present", [True, False])
def test_data_point_list(
    mocked_cmd,
    mocked_responses: responses,
    data_points_present
):
    dataset_name = "default"
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    dataset = {"name": dataset_name}
    if data_points_present:
        dataset["dataPoints"] = [{generate_random_string(): generate_random_string()}]
    mock_asset_record["properties"]["datasets"] = [dataset]

    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    result = list_asset_data_points(
        cmd=mocked_cmd,
        dataset_name=dataset_name,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )
    assert result == dataset.get("dataPoints", [])


def test_data_point_remove(
    mocked_cmd,
    mocked_responses: responses,
    mocked_check_cluster_connectivity,
):
    dataset_name = "default"
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    data_point_name = generate_random_string()
    alt_data_point_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    dataset = {
        "name": dataset_name,
        "dataPoints": [
            {
                "name": data_point_name,
                generate_random_string(): generate_random_string()
            },
            {
                "name": alt_data_point_name,
                generate_random_string(): generate_random_string()
            }
        ]
    }
    mock_asset_record["properties"]["datasets"] = [dataset]
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    result_datapoints = [{generate_random_string(): generate_random_string()}]
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json={"properties": {"datasets": [{
            "name": dataset_name,
            "dataPoints": result_datapoints
        }]}},
        status=200,
        content_type="application/json",
    )
    result = remove_asset_data_point(
        cmd=mocked_cmd,
        dataset_name=dataset_name,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        data_point_name=data_point_name,
        wait_sec=0,
    )
    assert result == result_datapoints
    datasets = json.loads(mocked_responses.calls[-1].request.body)["properties"]["datasets"]
    assert datasets
    point_names = [point["name"] for point in datasets[0]["dataPoints"]]
    assert data_point_name not in point_names
    assert alt_data_point_name in point_names


# Events
@pytest.mark.parametrize("observability_mode", [None, "log"])
@pytest.mark.parametrize("queue_size", [True, 2])
@pytest.mark.parametrize("sampling_interval", [True, 1000])
@pytest.mark.parametrize("replace", [False, True])
def test_event_add(
    mocked_cmd,
    mocked_responses: responses,
    mocked_check_cluster_connectivity,
    observability_mode,
    queue_size,
    sampling_interval,
    replace
):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    event_name = generate_random_string()
    event_notifier = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )

    if replace:
        mock_asset_record["events"] = [{
            "name": event_name, generate_random_string(): generate_random_string()
        }]
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    result_events = [{generate_random_string(): generate_random_string()}]
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json={"properties": {"events": result_events}},
        status=200,
        content_type="application/json",
    )
    result = add_asset_event(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        event_notifier=event_notifier,
        observability_mode=observability_mode,
        queue_size=queue_size,
        sampling_interval=sampling_interval,
        wait_sec=0,
    )
    assert result == result_events
    events = json.loads(mocked_responses.calls[-1].request.body)["properties"]["events"]
    assert events
    assert events[-1]["name"] == event_name
    assert events[-1]["eventNotifier"] == event_notifier
    assert events[-1]["observabilityMode"] == (observability_mode or "none").capitalize()
    custom_config = json.loads(events[-1]["eventConfiguration"])
    assert custom_config.get("queueSize") == queue_size
    assert custom_config.get("samplingInterval") == sampling_interval


def test_event_add_error(
    mocked_cmd,
    mocked_responses: responses,
    mocked_check_cluster_connectivity,
):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    event_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    mock_asset_record["properties"]["events"] = [
        {"name": event_name, generate_random_string(): generate_random_string()},
        {"name": generate_random_string(), generate_random_string(): generate_random_string()}
    ]
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    with pytest.raises(InvalidArgumentValueError):
        add_asset_event(
            cmd=mocked_cmd,
            asset_name=asset_name,
            resource_group_name=resource_group_name,
            event_name=event_name,
            event_notifier=generate_random_string(),
            wait_sec=0,
        )


@pytest.mark.parametrize("events_present", [True, False])
@pytest.mark.parametrize("extension", FileType.list())
@pytest.mark.parametrize("output_dir", [None, generate_random_string()])
@pytest.mark.parametrize("replace", [False, True])
def test_event_export(
    mocked_cmd,
    mocked_responses: responses,
    mocked_dump_content_to_file,
    events_present,
    extension,
    output_dir,
    replace,
):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    if events_present:
        mock_asset_record["properties"]["events"] = [
            {
                "eventConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
                "eventNotifier": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            },
            {
                "eventConfiguration": "{}",
                "name": generate_random_string(),
                "eventNotifier": generate_random_string(),
            },
            {
                "eventConfiguration": "{\"samplingInterval\": 100}",
                "eventNotifier": generate_random_string(),
                "name": generate_random_string(),
                "observabilityMode": generate_random_string()
            }
        ]

    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    result = export_asset_events(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        extension=extension,
        output_dir=output_dir,
        replace=replace
    )
    assert result["file_path"] == mocked_dump_content_to_file.return_value

    default_config = mock_asset_record["properties"].get("defaultEventsConfiguration", "{}")
    expected_fieldnames = None
    if extension in [FileType.csv.value]:
        from azext_edge.edge.providers.rpsaas.adr.assets import _convert_sub_points_to_csv
        expected_fieldnames = _convert_sub_points_to_csv(
            sub_points=mock_asset_record["properties"].get("events", []),
            sub_point_type="events",
            default_configuration=default_config,
            portal_friendly=True
        )

    call_kwargs = mocked_dump_content_to_file.call_args.kwargs
    assert call_kwargs["content"] == mock_asset_record["properties"].get("events", [])
    assert call_kwargs["file_name"] == f"{asset_name}_events"
    assert call_kwargs["extension"] == extension.replace("-", ".")
    assert call_kwargs["fieldnames"] == expected_fieldnames
    assert call_kwargs["output_dir"] == output_dir
    assert call_kwargs["replace"] == replace


@pytest.mark.parametrize("replace", [False, True])
def test_event_import(
    mocker,
    mocked_cmd,
    mocked_responses: responses,
    mocked_check_cluster_connectivity,
    mocked_deserialize_file_content,
    replace
):
    # remove logger warnings
    mocker.patch("azext_edge.edge.providers.rpsaas.adr.assets.logger")
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    dup_name = generate_random_string()
    file_path = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    file_events = [
        {
            "eventConfiguration": "{\"samplingInterval\": 300, \"queueSize\": 30}",
            "eventNotifier": generate_random_string(),
            "name": dup_name,
            "observabilityMode": generate_random_string()
        },
        {
            "eventConfiguration": "{\"samplingInterval\": 100}",
            "eventNotifier": generate_random_string(),
            "name": generate_random_string(),
            "observabilityMode": generate_random_string()
        }
    ]
    cloud_events = [
        {
            "eventConfiguration": "{\"samplingInterval\": 100, \"queueSize\": 50}",
            "eventNotifier": generate_random_string(),
            "name": dup_name,
            "observabilityMode": generate_random_string()
        },
        {
            "eventConfiguration": "{}",
            "name": generate_random_string(),
            "eventNotifier": generate_random_string(),
        }
    ]
    mocked_deserialize_file_content.return_value = file_events
    mock_asset_record["properties"]["events"] = cloud_events
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    result_events = [{generate_random_string(): generate_random_string()}]
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json={"properties": {"events": result_events}},
        status=200,
        content_type="application/json",
    )
    result = import_asset_events(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        file_path=file_path,
        replace=replace,
        wait_sec=0,
    )

    assert result == result_events
    mocked_deserialize_file_content.assert_called_once_with(file_path=file_path)
    events = json.loads(mocked_responses.calls[-1].request.body)["properties"]["events"]
    assert events
    point_map = {point["name"]: point for point in events}
    assert file_events[1]["name"] in point_map
    assert dup_name in point_map
    # check the duplicate point
    if replace:
        point = file_events[0]
        assert file_events[1]["name"] in point_map
    else:
        point = cloud_events[0]
    assert cloud_events[1]["name"] in point_map
    assert point_map[dup_name]["eventConfiguration"] == point["eventConfiguration"]
    assert point_map[dup_name]["eventNotifier"] == point["eventNotifier"]
    assert point_map[dup_name]["observabilityMode"] == point["observabilityMode"]


@pytest.mark.parametrize("events_present", [True, False])
def test_event_list(
    mocked_cmd,
    mocked_responses: responses,
    events_present
):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    if events_present:
        mock_asset_record["properties"]["events"] = [{generate_random_string(): generate_random_string()}]

    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )

    result = list_asset_events(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name
    )
    assert result == mock_asset_record["properties"].get("events", [])


def test_event_remove(
    mocked_cmd,
    mocked_responses: responses,
    mocked_check_cluster_connectivity,
):
    asset_name = generate_random_string()
    resource_group_name = generate_random_string()
    event_name = generate_random_string()
    alt_event_name = generate_random_string()
    mock_asset_record = get_asset_record(
        asset_name=asset_name, asset_resource_group=resource_group_name
    )
    mock_asset_record["properties"]["events"] = [
        {
            "name": event_name,
            generate_random_string(): generate_random_string()
        },
        {
            "name": alt_event_name,
            generate_random_string(): generate_random_string()
        }
    ]
    mocked_responses.add(
        method=responses.GET,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json=mock_asset_record,
        status=200,
        content_type="application/json",
    )
    result_events = [{generate_random_string(): generate_random_string()}]
    mocked_responses.add(
        method=responses.PUT,
        url=get_asset_mgmt_uri(asset_name=asset_name, asset_resource_group=resource_group_name),
        json={"properties": {"events": result_events}},
        status=200,
        content_type="application/json",
    )
    result = remove_asset_event(
        cmd=mocked_cmd,
        asset_name=asset_name,
        resource_group_name=resource_group_name,
        event_name=event_name,
        wait_sec=0,
    )
    assert result == result_events
    events = json.loads(mocked_responses.calls[-1].request.body)["properties"]["events"]
    assert events
    event_names = [event["name"] for event in events]
    assert event_name not in event_names
    assert alt_event_name in event_names
