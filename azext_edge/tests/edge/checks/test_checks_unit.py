# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
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

    target_1 = generate_generic_id()
    target_1_condition_1 = generate_generic_id()
    target_1_conditions = [target_1_condition_1]
    target_1_eval_1_value = {generate_generic_id(): generate_generic_id()}
    target_1_display_1 = generate_generic_id()

    check_manager.add_target(target_name=target_1, conditions=target_1_conditions)
    check_manager.add_target_eval(
        target_name=target_1, status=CheckTaskStatus.success.value, value=target_1_eval_1_value
    )
    check_manager.add_display(target_name=target_1, display=target_1_display_1)
    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [{"status": CheckTaskStatus.success.value, "value": target_1_eval_1_value}],
            "status": CheckTaskStatus.success.value,
        }
    }
    assert_check_manager_dict(
        check_manager=check_manager,
        expected_name=name,
        expected_desc=desc,
        expected_targets=expected_targets,
        expected_target_displays={target_1: [target_1_display_1]},
    )
    check_manager.add_target_eval(target_name=target_1, status=CheckTaskStatus.warning.value)
    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [
                {"status": CheckTaskStatus.success.value, "value": target_1_eval_1_value},
                {"status": CheckTaskStatus.warning.value},
            ],
            "status": CheckTaskStatus.warning.value,
        }
    }
    assert_check_manager_dict(
        check_manager=check_manager,
        expected_name=name,
        expected_desc=desc,
        expected_targets=expected_targets,
        expected_status=CheckTaskStatus.warning.value,
    )

    target_2 = generate_generic_id()
    target_2_condition_1 = generate_generic_id()
    target_2_conditions = [target_2_condition_1]
    check_manager.add_target(target_name=target_2, conditions=target_2_conditions)
    check_manager.add_target_eval(target_name=target_2, status=CheckTaskStatus.error.value)

    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [
                {"status": CheckTaskStatus.success.value, "value": target_1_eval_1_value},
                {"status": CheckTaskStatus.warning.value},
            ],
            "status": CheckTaskStatus.warning.value,
        },
        target_2: {
            "conditions": target_2_conditions,
            "evaluations": [{"status": CheckTaskStatus.error.value}],
            "status": CheckTaskStatus.error.value,
        },
    }
    assert_check_manager_dict(
        check_manager=check_manager,
        expected_name=name,
        expected_desc=desc,
        expected_targets=expected_targets,
        expected_status=CheckTaskStatus.error.value,
    )

    # Re-create check manager with target 1 kpis and assert skipped status
    check_manager = CheckManager(check_name=name, check_desc=desc, namespace=namespace)
    check_manager.add_target(target_name=target_1, conditions=target_1_conditions)
    check_manager.add_target_eval(target_name=target_1, status=CheckTaskStatus.skipped.value, value=None)
    expected_targets = {
        target_1: {
            "conditions": target_1_conditions,
            "evaluations": [{"status": CheckTaskStatus.skipped.value}],
            "status": CheckTaskStatus.skipped.value,
        }
    }
    assert_check_manager_dict(
        check_manager=check_manager,
        expected_name=name,
        expected_desc=desc,
        expected_targets=expected_targets,
        expected_status=CheckTaskStatus.skipped.value,
    )


def assert_check_manager_dict(
    check_manager: CheckManager,
    expected_name: str,
    expected_desc: str,
    expected_targets: dict = None,
    expected_status: str = CheckTaskStatus.success.value,
    expected_target_displays: dict = None,
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

    if expected_target_displays:
        result_check_dict_displays = check_manager.as_dict(as_list=True)
        for target in expected_target_displays:
            assert expected_target_displays[target] == result_check_dict_displays["targets"][target]["displays"]
