# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from unittest.mock import call

from azext_edge.edge.common import CheckTaskStatus
from azext_edge.edge.providers.check.base import (
    enumerate_ops_service_resources,
    filter_resources_by_name,
    generate_target_resource_name,
    get_resources_by_name,
    get_resource_metadata_property,
    process_dict_resource,
    process_list_resource,
    process_resource_properties,
    validate_one_of_conditions,
    process_custom_resource_status,
)
from azext_edge.edge.providers.check.base.resource import (
    calculate_status,
    combine_statuses,
    process_resource_property_by_type,
)
from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET, ResourceOutputDetailLevel
from azext_edge.edge.providers.edge_api import (
    AKRI_API_V0,
    AkriResourceKinds,
    MQ_ACTIVE_API,
    MqResourceKinds,
    OPCUA_API_V1,
    OpcuaResourceKinds,
)
from azext_edge.edge.providers.edge_api.deviceregistry import DEVICEREGISTRY_API_V1, DeviceRegistryResourceKinds
from azext_edge.tests.edge.checks.conftest import generate_api_resource_list, generate_pod_stub


@pytest.mark.parametrize(
    "api_info, resource_kinds, check_name, check_desc,\
        excluded_resources, api_resources, expected_resource_map, status",
    [
        (MQ_ACTIVE_API, MqResourceKinds.list(), "mq", "MQ", None, [], {}, CheckTaskStatus.error.value),
        (
            AKRI_API_V0,
            AkriResourceKinds.list(),
            "akri",
            "AKRI",
            None,
            generate_api_resource_list(
                api_version=AKRI_API_V0.version,
                group_version=AKRI_API_V0.as_str(),
                resources=[
                    {
                        "categories": None,
                        "group": None,
                        "kind": "Instance",
                        "name": "instances",
                        "namespaced": True,
                        "short_names": ["akrii"],
                        "singular_name": "instance",
                        "verbs": ["delete", "deletecollection", "get", "list", "patch", "create", "update", "watch"],
                    },
                    {
                        "categories": None,
                        "group": None,
                        "kind": "Configuration",
                        "name": "configurations",
                        "namespaced": True,
                        "short_names": ["akric"],
                        "singular_name": "configuration",
                        "verbs": ["delete", "deletecollection", "get", "list", "patch", "create", "update", "watch"],
                    },
                ],
            ),
            {
                AkriResourceKinds.INSTANCE.value.capitalize(): True,
                AkriResourceKinds.CONFIGURATION.value.capitalize(): True,
            },
            CheckTaskStatus.success.value,
        ),
        (
            OPCUA_API_V1,
            OpcuaResourceKinds.list(),
            "opcua",
            "OPCUA",
            ["assettypes"],
            generate_api_resource_list(
                api_version=OPCUA_API_V1.version,
                group_version=OPCUA_API_V1.as_str(),
                resources=[
                    {
                        "categories": None,
                        "group": None,
                        "kind": "AssetType",
                        "name": "assettypes",
                        "namespaced": True,
                        "short_names": None,
                        "singular_name": "assettype",
                        "storage_version_hash": "FCPRUJA7s2I=",
                        "verbs": ["delete", "deletecollection", "get", "list", "patch", "create", "update", "watch"],
                        "version": None,
                    },
                ],
            ),
            {},
            CheckTaskStatus.success.value,
        ),
    ],
)
def test_enumerate_ops_service_resources(
    mock_get_cluster_custom_api,
    api_info,
    resource_kinds,
    api_resources,
    check_name,
    check_desc,
    excluded_resources,
    expected_resource_map,
    status,
):
    mock_get_cluster_custom_api.return_value = api_resources
    result, resource_map = enumerate_ops_service_resources(
        api_info=api_info,
        check_name=check_name,
        check_desc=check_desc,
        as_list=False,
        excluded_resources=excluded_resources,
    )
    assert len(result["targets"][api_info.as_str()]) == 1
    target_key = f"{api_info.group}/{api_info.version}"
    assert target_key in result["targets"]
    evaluation = result["targets"][api_info.as_str()][ALL_NAMESPACES_TARGET]
    assert evaluation["conditions"] is None
    assert evaluation["status"] == status
    assert len(evaluation["evaluations"]) == 1
    assert evaluation["evaluations"][0]["status"] == status
    assert resource_map == expected_resource_map

    if status == expected_resource_map:
        assert len(evaluation["evaluations"][0]["value"]) == len(resource_kinds)
        for kind in evaluation["evaluations"][0]["value"]:
            assert kind.lower() in resource_kinds


@pytest.mark.parametrize(
    "resource_list, resource_name, expected_resources",
    [
        (
            [
                {"metadata": {"name": "test1"}},
                {"metadata": {"name": "test2"}},
                {"metadata": {"name": "test3"}},
            ],
            None,
            [
                {"metadata": {"name": "test1"}},
                {"metadata": {"name": "test2"}},
                {"metadata": {"name": "test3"}},
            ],
        ),
        (
            [
                {"metadata": {"name": "test1"}},
                {"metadata": {"name": "test2"}},
                {"metadata": {"name": "test3"}},
            ],
            "test",
            [],
        ),
        (
            [
                {"metadata": {"name": "test1"}},
                {"metadata": {"name": "test2"}},
                {"metadata": {"name": "test3"}},
            ],
            "test*",
            [
                {"metadata": {"name": "test1"}},
                {"metadata": {"name": "test2"}},
                {"metadata": {"name": "test3"}},
            ],
        ),
        (
            [
                {"metadata": {"name": "test1"}},
                {"metadata": {"name": "test2"}},
                {"metadata": {"name": "test3"}},
            ],
            "test4",
            [],
        ),
    ],
)
def test_filter_resources_by_name(
    resource_list,
    resource_name,
    expected_resources,
):
    result = filter_resources_by_name(resource_list, resource_name)
    assert result == expected_resources


@pytest.mark.parametrize(
    "api_info, resource_kind, expected_name",
    [
        (DEVICEREGISTRY_API_V1, DeviceRegistryResourceKinds.ASSET.value, "assets.deviceregistry.microsoft.com"),
        (DEVICEREGISTRY_API_V1, "mocktype", "mocktypes.deviceregistry.microsoft.com"),
    ],
)
def test_generate_target_resource_name(api_info, resource_kind, expected_name):
    result = generate_target_resource_name(api_info, resource_kind)
    assert result == expected_name


@pytest.mark.parametrize(
    "kind, resource_name, namespace, returned_resources, expected_filtered_resources",
    [
        (
            "asset",
            "test*",
            "namespace",
            [{"metadata": {"name": "test1"}}, {"metadata": {"name": "test2"}}, {"metadata": {"name": "nontest"}}],
            [{"metadata": {"name": "test1"}}, {"metadata": {"name": "test2"}}],
        ),
        (
            "asset",
            "asset1",
            "default",
            [
                {"metadata": {"name": "asset1", "namespace": "default"}},
                {"metadata": {"name": "asset2", "namespace": "default"}},
            ],
            [{"metadata": {"name": "asset1", "namespace": "default"}}],
        ),
        ("asset", "nonexistent", None, [{"metadata": {"name": "test1"}}, {"metadata": {"name": "test2"}}], []),
    ],
)
def test_get_resources_by_name(
    mocker, kind, resource_name, namespace, returned_resources, expected_filtered_resources
):
    # Set up the mock
    api_info_patch = mocker.patch("azext_edge.edge.providers.edge_api.EdgeResourceApi")
    api_info_patch.get_resources.return_value = {"items": returned_resources}

    patched = mocker.patch(
        "azext_edge.edge.providers.check.base.resource.filter_resources_by_name",
        return_value=expected_filtered_resources,
    )

    result = get_resources_by_name(api_info_patch, kind, resource_name, namespace)

    # Assert the results
    assert result == expected_filtered_resources
    patched.assert_called_once_with(returned_resources, resource_name)


@pytest.mark.parametrize(
    "resource, prop_name, expected_value",
    [
        ({"metadata": {"name": "test1"}}, "name", "test1"),  # Dictionary with property
        ({"metadata": {"name": "test1"}}, "namespace", None),  # Dictionary without property
        (
            generate_pod_stub(
                name="test2",
                phase="Running",
            ),
            "name",
            "test2",
        ),  # Pod with metadata property
        ({"not_metadata": {"name": "test3"}}, "name", None),  # Dictionary without metadata
        ("string_resource", "name", None),  # Non-dictionary and non-object resource
    ],
)
def test_get_resource_metadata_property(resource, prop_name, expected_value):
    result = get_resource_metadata_property(resource, prop_name)
    assert result == expected_value


@pytest.mark.parametrize(
    "resource, prop_name, expected_calls",
    [
        (
            {"key1": "value1", "key2": {"nested_key": "nested_value"}},
            None,
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "key1: [cyan]value1[/cyan]",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "key2:",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "nested_key: [cyan]nested_value[/cyan]",
                },
            ],
        ),
        (
            {"key1": "a" * 51},
            None,
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "key1: ",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": f"[cyan]{'a' * 51}[/cyan]",
                },
            ],
        ),
        (
            {"list_key": ["item1", "item2"]},
            None,
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "list_key:",
                },
            ],
        ),
        (
            {},
            "test_prop",
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "test_prop:",
                },
            ],
        ),
    ],
)
def test_process_dict_resource(mocker, mocked_check_manager, resource, prop_name, expected_calls):
    mocker.patch("azext_edge.edge.providers.check.base.display.process_value_color", return_value="value")
    mock_process_list_resource = mocker.patch(
        "azext_edge.edge.providers.check.base.resource.process_list_resource", return_value=None
    )
    process_dict_resource(
        check_manager=mocked_check_manager,
        target_name="test_target",
        resource=resource,
        namespace="test_namespace",
        padding=0,
        prop_name=prop_name,
    )

    # Verify the expected calls to check_manager.add_display
    call_args_list = mocked_check_manager.add_display.call_args_list
    for call_args, expected in zip(call_args_list, expected_calls):
        assert call_args.kwargs["target_name"] == expected["target_name"]
        assert call_args.kwargs["namespace"] == expected["namespace"]
        assert call_args.kwargs["display"].renderable == expected["displayText"]

    if any(isinstance(value, list) for value in resource.values()):
        assert mock_process_list_resource.called
    else:
        assert not mock_process_list_resource.called


@pytest.mark.parametrize(
    "resource, expected_calls",
    [
        (
            [{"name": "item1"}, {"name": "item2"}],
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "- name: [cyan]item1[/cyan]",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "- name: [cyan]item2[/cyan]",
                },
            ],
        ),
        (
            [{"name": "item1"}, "string_item2"],
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "- name: [cyan]item1[/cyan]",
                },
                {"target_name": "test_target", "namespace": "test_namespace", "displayText": "- item 2"},
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "[cyan]string_item2[/cyan]",
                },
            ],
        ),
        (
            [{"nested_dict": {"name": "nested_item"}}, {"name": "item2"}],
            [
                {"target_name": "test_target", "namespace": "test_namespace", "displayText": "- item 1"},
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "- name: [cyan]item2[/cyan]",
                },
            ],
        ),
        (
            ["string_item1", "string_item2"],
            [
                {"target_name": "test_target", "namespace": "test_namespace", "displayText": "- item 1"},
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "[cyan]string_item1[/cyan]",
                },
                {"target_name": "test_target", "namespace": "test_namespace", "displayText": "- item 2"},
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "[cyan]string_item2[/cyan]",
                },
            ],
        ),
    ],
)
def test_process_list_resource(mocker, mocked_check_manager, resource, expected_calls):
    mock_process_dict_resource = mocker.patch(
        "azext_edge.edge.providers.check.base.resource.process_dict_resource", return_value=None
    )

    # Call the function being tested
    process_list_resource(
        check_manager=mocked_check_manager,
        target_name="test_target",
        resource=resource,
        namespace="test_namespace",
        padding=0,
    )

    # Verify the expected calls to check_manager.add_display
    call_args_list = mocked_check_manager.add_display.call_args_list
    for call_args, expected in zip(call_args_list, expected_calls):
        assert call_args.kwargs["target_name"] == expected["target_name"]
        assert call_args.kwargs["namespace"] == expected["namespace"]
        assert call_args.kwargs["display"].renderable == expected["displayText"]

    # Verify calls to process_dict_resource
    if any(isinstance(item, dict) for item in resource):
        assert mock_process_dict_resource.called
    else:
        assert not mock_process_dict_resource.called


@pytest.mark.parametrize(
    "detail_level, prop_value, properties, expected_calls",
    [
        (
            ResourceOutputDetailLevel.verbose,
            {"key1": "value1", "descriptor": "detailed_description"},
            [("key1", "Display Name 1", False), ("descriptor", "Descriptor", True)],
            [
                {
                    "target_name": "test_target",
                    "properties": "value1",
                    "display_name": "Display Name 1",
                    "namespace": "test_namespace",
                    "padding": (0, 0, 0, 0),
                },
                {
                    "target_name": "test_target",
                    "properties": "detailed_description",
                    "display_name": "Descriptor",
                    "namespace": "test_namespace",
                    "padding": (0, 0, 0, 0),
                },
            ],
        ),
        (
            ResourceOutputDetailLevel.summary,
            {"key1": "value1", "descriptor": "detailed_description"},
            [("key1", "Display Name 1", False), ("descriptor", "Descriptor", True)],
            [
                {
                    "target_name": "test_target",
                    "properties": "value1",
                    "display_name": "Display Name 1",
                    "namespace": "test_namespace",
                    "padding": (0, 0, 0, 0),
                },
            ],
        ),
        (
            ResourceOutputDetailLevel.summary,
            {"nested": {"key2": "nested_value2"}},
            [("nested.key2", "Nested Display Name 2", False)],
            [
                {
                    "target_name": "test_target",
                    "properties": "nested_value2",
                    "display_name": "Nested Display Name 2",
                    "namespace": "test_namespace",
                    "padding": (0, 0, 0, 0),
                },
            ],
        ),
        (
            ResourceOutputDetailLevel.verbose,
            {"key3": "value3"},
            [("key4", "Display Name 4", False)],
            [],
        ),
    ],
)
def test_process_resource_properties(
    mocker, mocked_check_manager, detail_level, prop_value, properties, expected_calls
):
    mock_process_resource_property = mocker.patch(
        "azext_edge.edge.providers.check.base.resource.process_resource_property_by_type", autospec=True
    )
    padding = (0, 0, 0, 0)

    process_resource_properties(
        check_manager=mocked_check_manager,
        detail_level=detail_level,
        target_name="test_target",
        prop_value=prop_value,
        properties=properties,
        namespace="test_namespace",
        padding=padding,
    )

    # Verify the expected calls to process_resource_property_by_type
    call_args_list = mock_process_resource_property.call_args_list
    for call_args, expected in zip(call_args_list, expected_calls):
        kwargs = call_args.kwargs
        assert kwargs["target_name"] == expected["target_name"]
        assert kwargs["properties"] == expected["properties"]
        assert kwargs["display_name"] == expected["display_name"]
        assert kwargs["namespace"] == expected["namespace"]
        assert kwargs["padding"] == expected["padding"]


@pytest.mark.parametrize(
    "properties, display_name, padding, expected_calls",
    [
        # Test case for list of dictionaries
        (
            [{"prop1": "value1"}, {"prop2": "value2"}],
            "Test List",
            (0, 0, 0, 0),
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "Test List:",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "- Test List 1",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "prop1: [cyan]value1[/cyan]",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "- Test List 2",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "prop2: [cyan]value2[/cyan]",
                },
            ],
        ),
        # Test case for short string
        (
            "short_string",
            "Test String",
            (0, 0, 0, 0),
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "Test String: [cyan]short_string[/cyan]",
                },
            ],
        ),
        # Test case for long string
        (
            "a" * 51,
            "Long String",
            (0, 0, 0, 0),
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "Long String:",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "[cyan]aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa[/cyan]",
                },
            ],
        ),
        # Test case for boolean
        (
            True,
            "Test Bool",
            (0, 0, 0, 0),
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "Test Bool: [cyan]True[/cyan]",
                },
            ],
        ),
        # Test case for integer
        (
            123,
            "Test Int",
            (0, 0, 0, 0),
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "Test Int: [cyan]123[/cyan]",
                },
            ],
        ),
        # Test case for dictionary
        (
            {"key1": "value1", "key2": "value2"},
            "Test Dict",
            (0, 0, 0, 0),
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "Test Dict:",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "key1: [cyan]value1[/cyan]",
                },
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "key2: [cyan]value2[/cyan]",
                },
            ],
        ),
    ],
)
def test_process_resource_property_by_type(mocked_check_manager, properties, display_name, padding, expected_calls):
    # Call the function being tested
    process_resource_property_by_type(
        check_manager=mocked_check_manager,
        target_name="test_target",
        properties=properties,
        display_name=display_name,
        namespace="test_namespace",
        padding=padding,
    )

    # Verify the expected calls to check_manager.add_display
    call_args_list = mocked_check_manager.add_display.call_args_list
    for call_args, expected in zip(call_args_list, expected_calls):
        actual_call = call_args[1]  # call_args[1] contains the kwargs
        assert actual_call["target_name"] == expected["target_name"]
        assert actual_call["namespace"] == expected["namespace"]
        assert actual_call["display"].renderable == expected["displayText"]


@pytest.mark.parametrize(
    "conditions, expected_display_calls, expected_conditions_calls, expected_eval_calls",
    [
        (
            [("cond1", True), ("cond2", False)],
            [],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    conditions=["oneOf('cond1', 'cond2')"],
                ),
            ],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    status=CheckTaskStatus.success.value,
                    value={"eval_key": "eval_value"},
                    resource_name="test_resource",
                ),
            ],
        ),
        (
            [("cond1", False), ("cond2", False)],
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "One of 'cond1', 'cond2' should be specified",
                },
            ],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    conditions=["oneOf('cond1', 'cond2')"],
                ),
            ],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    status=CheckTaskStatus.error.value,
                    value={"eval_key": "eval_value"},
                    resource_name="test_resource",
                ),
            ],
        ),
        (
            [("cond1", True), ("cond2", True)],
            [
                {
                    "target_name": "test_target",
                    "namespace": "test_namespace",
                    "displayText": "Only one of 'cond1', 'cond2' should be specified",
                },
            ],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    conditions=["oneOf('cond1', 'cond2')"],
                ),
            ],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    status=CheckTaskStatus.error.value,
                    value={"eval_key": "eval_value"},
                    resource_name="test_resource",
                ),
            ],
        ),
        (
            [("cond1", True)],
            [],
            [],
            [],
        ),
    ],
)
def test_validate_one_of_conditions(
    mocked_check_manager, conditions, expected_display_calls, expected_conditions_calls, expected_eval_calls
):

    validate_one_of_conditions(
        conditions=conditions,
        check_manager=mocked_check_manager,
        eval_value={"eval_key": "eval_value"},
        namespace="test_namespace",
        target_name="test_target",
        padding=4,
        resource_name="test_resource",
    )

    # Verify the expected calls to check_manager.add_display
    display_call_args_list = mocked_check_manager.add_display.call_args_list
    for call_args, expected in zip(display_call_args_list, expected_display_calls):
        assert call_args.kwargs["target_name"] == expected["target_name"]
        assert call_args.kwargs["namespace"] == expected["namespace"]
        assert call_args.kwargs["display"].renderable == expected["displayText"]

    # Verify the expected calls to check_manager.add_target_conditions
    assert mocked_check_manager.add_target_conditions.call_args_list == expected_conditions_calls

    # Verify the expected calls to check_manager.add_target_eval
    assert mocked_check_manager.add_target_eval.call_args_list == expected_eval_calls


@pytest.mark.parametrize(
    "status_list, expected_final_status",
    [
        (["Succeeded", "Succeeded", "Succeeded"], "success"),
        (["Warning", "Error", "Success"], "error"),
        (["Warning", "Warning", "Success"], "warning"),
        (["Success", "Success", "Error"], "error"),
    ],
)
def test_combine_statuses(status_list, expected_final_status):
    assert combine_statuses(status_list) == expected_final_status


@pytest.mark.parametrize(
    "resource_state, expected_status",
    [
        ("Starting", "warning"),
        ("Running", "success"),
        ("Recovering", "warning"),
        ("Succeeded", "success"),
        ("Failed", "error"),
        ("Waiting", "warning"),
        ("OK", "success"),
        ("warn", "warning"),
        ("Error", "error"),
        ("N/A", "warning"),
    ],
)
def test_calculate_status(resource_state, expected_status):
    # Call the function being tested
    result = calculate_status(resource_state)

    # Verify the result
    assert result == expected_status


@pytest.mark.parametrize(
    "status, detail_level, expected_display_texts, expected_conditions_calls, expected_eval_calls",
    [
        # Scenario 1: Both runtimeStatus and provisioningStatus are provided with summary detail level.
        (
            {
                "runtimeStatus": {"status": "Running", "statusDescription": "All good"},
                "provisioningStatus": {"status": "Success"},
            },
            ResourceOutputDetailLevel.summary.value,
            ["Status {[green]success[/green]}."],
            [call(target_name="test_target", namespace="test_namespace", conditions=["status"])],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    status="success",
                    value={
                        "status": {
                            "runtimeStatus": {"status": "Running", "statusDescription": "All good"},
                            "provisioningStatus": {"status": "Success"},
                        }
                    },
                    resource_name="test_resource",
                )
            ],
        ),
        # Scenario 2: No runtimeStatus and provisioningStatus provided.
        (
            {"runtimeStatus": {}, "provisioningStatus": {}},
            ResourceOutputDetailLevel.summary.value,
            ["Status [red]not found[/red]."],
            [call(target_name="test_target", namespace="test_namespace", conditions=["status"])],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    status=CheckTaskStatus.error.value,
                    value={"status": {"runtimeStatus": {}, "provisioningStatus": {}}},
                    resource_name="test_resource",
                )
            ],
        ),
        # Scenario 3: Both statuses, verbose detail level.
        (
            {
                "runtimeStatus": {"status": "Running", "statusDescription": "All good"},
                "provisioningStatus": {"status": "Success"},
            },
            ResourceOutputDetailLevel.verbose.value,
            [
                "Status:",
                "Provisioning Status {[green]Success[/green]}.",
                "Runtime Status {[green]Running[/green]}, [cyan]All good[/cyan].",
            ],
            [call(target_name="test_target", namespace="test_namespace", conditions=["status"])],
            [
                call(
                    target_name="test_target",
                    namespace="test_namespace",
                    status="success",
                    value={
                        "status": {
                            "runtimeStatus": {"status": "Running", "statusDescription": "All good"},
                            "provisioningStatus": {"status": "Success"},
                        }
                    },
                    resource_name="test_resource",
                )
            ],
        ),
    ],
)
def test_process_custom_resource_status(
    mocker,
    mocked_check_manager,
    status,
    detail_level,
    expected_display_texts,
    expected_conditions_calls,
    expected_eval_calls,
):
    mocker.patch("azext_edge.edge.providers.check.base.resource.combine_statuses", return_value="success")
    mocker.patch("azext_edge.edge.providers.check.base.resource.calculate_status", return_value="success")
    mocker.patch(
        "azext_edge.edge.providers.check.base.resource.decorate_resource_status",
        side_effect=lambda status: f"[green]{status}[/green]",
    )

    process_custom_resource_status(
        check_manager=mocked_check_manager,
        status=status,
        target_name="test_target",
        namespace="test_namespace",
        resource_name="test_resource",
        padding=5,
        detail_level=detail_level,
    )

    # Verify the expected display texts
    display_call_args_list = mocked_check_manager.add_display.call_args_list
    for call_args, expected_text in zip(display_call_args_list, expected_display_texts):
        assert call_args.kwargs["display"].renderable == expected_text

    # Verify the expected calls to add_target_conditions
    assert mocked_check_manager.add_target_conditions.call_args_list == expected_conditions_calls

    # Verify the expected calls to add_target_eval
    assert mocked_check_manager.add_target_eval.call_args_list == expected_eval_calls
