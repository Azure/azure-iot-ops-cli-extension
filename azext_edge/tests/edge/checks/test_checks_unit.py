# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# PRIVATE DISTRIBUTION FOR NDA CUSTOMERS ONLY
# --------------------------------------------------------------------------------------------


from azext_edge.edge.providers.checks import CheckManager
from azext_edge.edge.common import CheckTaskStatus
from ...generators import generate_generic_id


def test_check_manager():
    name = generate_generic_id()
    desc = f"{generate_generic_id()} {generate_generic_id()}"
    namespace = generate_generic_id()
    check_manager = CheckManager(check_name=name, check_desc=desc, namespace=namespace)
    assert_check_manager_dict(check_manager=check_manager, expected_name=name, expected_desc=desc)
    
    target = generate_generic_id()
    check_manager.add_target()


def assert_check_manager_dict(
    check_manager: CheckManager,
    expected_name: str,
    expected_desc: str,
    expected_targets: dict = None,
    expected_status: str = CheckTaskStatus.success.value,
):
    result_check_dict = check_manager.as_dict()
    if not expected_targets:
        expected_targets = {}

    assert "name" in result_check_dict
    assert result_check_dict["name"] == expected_name

    assert "description" in result_check_dict
    assert result_check_dict["description"] == expected_desc

    assert "targets" in result_check_dict
    assert result_check_dict["targets"] == expected_targets

    assert "status" in result_check_dict
    assert result_check_dict["status"] == expected_status
