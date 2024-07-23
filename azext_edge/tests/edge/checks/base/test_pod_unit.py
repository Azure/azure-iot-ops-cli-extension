# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from rich.padding import Padding
from azext_edge.edge.common import CheckTaskStatus, PodState
from azext_edge.edge.providers.check.base import (
    decorate_pod_phase,
    evaluate_pod_health,
    process_pod_status,
)
from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET, ResourceOutputDetailLevel
from azext_edge.tests.edge.checks.conftest import generate_pod_stub
from ....generators import generate_random_string


@pytest.mark.parametrize("phase, expected", [
    ("Running", ("[green]Running[/green]", PodState.map_to_status("Running").value)),
    ("Pending", ("[yellow]Pending[/yellow]", PodState.map_to_status("Pending").value)),
    ("Failed", ("[red]Failed[/red]", PodState.map_to_status("Failed").value)),
    ("Succeeded", ("[green]Succeeded[/green]", PodState.map_to_status("Succeeded").value)),
    ("Unknown", ("[yellow]Unknown[/yellow]", PodState.map_to_status("Unknown").value))
])
def test_decorate_pod_phase(phase, expected):
    assert decorate_pod_phase(phase) == expected


@pytest.mark.parametrize("target_service_pod", [generate_random_string()])
@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("namespace", [ALL_NAMESPACES_TARGET, generate_random_string()])
@pytest.mark.parametrize("padding", [4])
@pytest.mark.parametrize(
    "pods",
    [
        [],
        [generate_pod_stub(name="mq-operator-1", phase="Running")],
        [generate_pod_stub(name="mq-operator-1", phase="Pending")],
        [generate_pod_stub(name="mq-operator-1", phase="Failed")],
        [
            generate_pod_stub(
                name="akri-operator-1",
                phase="Running",
            ),
            generate_pod_stub(
                name="akri-operator-2",
                phase="Pending",
            ),
        ],
        [
            generate_pod_stub(
                name="opcua-operator-1",
                phase="Running",
            ),
            generate_pod_stub(
                name="opcua-operator-3",
                phase="Failed",
            ),
        ],
    ]
)
def test_evaluate_pod_health(
    mocker,
    mock_process_pod_status,
    mocked_check_manager,
    namespace,
    padding,
    pods,
    target_service_pod,
    detail_level,
):
    mocker = mocker.patch(
        "azext_edge.edge.providers.check.base.pod.get_namespaced_pods_by_prefix",
        return_value=pods,
    )

    evaluate_pod_health(
        check_manager=mocked_check_manager,
        namespace=namespace,
        target=target_service_pod,
        pod=target_service_pod,
        display_padding=padding,
        service_label=generate_random_string(),
        detail_level=detail_level,
    )

    mock_process_pod_status.assert_called_once_with(
        check_manager=mocked_check_manager,
        namespace=namespace,
        target=target_service_pod,
        target_service_pod=f"pod/{target_service_pod}",
        pods=pods,
        display_padding=padding,
        detail_level=detail_level,
    )


@pytest.mark.parametrize("target_service_pod", [generate_random_string()])
@pytest.mark.parametrize("namespace", [ALL_NAMESPACES_TARGET, generate_random_string()])
@pytest.mark.parametrize("padding", [4])
@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("pods, eval_status, eval_value, resource_name", [
    (
        # pods
        None,
        # eval_status
        CheckTaskStatus.warning.value,
        # eval_value
        None,
        # resource_name
        "",
    ),
    (
        # pods
        [
            generate_pod_stub(
                name="akri-operator-1",
                phase="Running",
                conditions=[
                    {
                        "type": "Ready",
                        "status": "True",
                    },
                    {
                        "type": "Initialized",
                        "status": "True",
                    },
                    {
                        "type": "ContainersReady",
                        "status": "True",
                    },
                    {
                        "type": "PodScheduled",
                        "status": "True",
                    },
                ]
            ),
        ],
        # eval_status
        CheckTaskStatus.success.value,
        # eval_value
        {
            "status.conditions.ready": True,
            "status.conditions.initialized": True,
            "status.conditions.containersready": True,
            "status.conditions.podscheduled": True,
            "status.phase": "Running"
        },
        # resource_name
        "akri-operator-1",
    ),
    (
        # pods
        [
            generate_pod_stub(
                name="mq-operator-2",
                phase="Pending",
                conditions=[
                    {
                        "type": "PodReadyToStartContainers",
                        "status": "True",
                    }
                ]
            ),
        ],
        # eval_status
        CheckTaskStatus.warning.value,
        # eval_value
        {
            "status.conditions.podreadytostartcontainers": True,
            "status.phase": "Pending"
        },
        # resource_name
        "mq-operator-2",
    ),
    (
        # pods
        [
            generate_pod_stub(
                name="aio-operator-3",
                phase="Running",
                conditions=[
                    {
                        "type": "Ready",
                        "status": "False",
                    },
                    {
                        "type": "Initialized",
                        "status": "False",
                    },
                    {
                        "type": "ContainersReady",
                        "status": "False",
                    },
                    {
                        "type": "PodScheduled",
                        "status": "False",
                    },
                    {
                        "type": "PodReadyToStartContainers",
                        "status": "False",
                    }
                ]
            ),
        ],
        # eval_status
        CheckTaskStatus.error.value,
        # eval_value
        {
            "status.conditions.ready": False,
            "status.conditions.initialized": False,
            "status.conditions.containersready": False,
            "status.conditions.podscheduled": False,
            "status.conditions.podreadytostartcontainers": False,
            "status.phase": "Running"
        },
        # resource_name
        "aio-operator-3",
    ),
    (
        # pods
        [
            generate_pod_stub(
                name="opcua-operator-4",
                phase="Pending",
                conditions=[
                    {
                        "type": "Ready",
                        "status": "True",
                    },
                ]
            ),
        ],
        # eval_status
        CheckTaskStatus.warning.value,
        # eval_value
        {
            "status.conditions.ready": True,
            "status.phase": "Pending"
        },
        # resource_name
        "opcua-operator-4",
    ),
    (
        # pods
        [
            generate_pod_stub(
                name="mq-operator-5",
                phase="Failed",
                conditions=None
            ),
        ],
        # eval_status
        CheckTaskStatus.error.value,
        # eval_value
        {"status.phase": "Failed"},
        # resource_name
        "mq-operator-5",
    ),
    (
        # pods
        [
            generate_pod_stub(
                name="akri-operator-6",
                phase="Running",
                conditions=[
                    {
                        "type": "Ready",
                        "status": "True",
                    },
                    {
                        "type": "Initialized",
                        "status": "True",
                    },
                    {
                        "type": "ContainersReady",
                        "status": "True",
                    },
                    {
                        "type": "PodScheduled",
                        "status": "True",
                    },
                    {
                        "type": "UnknownCondition",
                        "status": "True",
                        "reason": "Unknown",
                    }
                ]
            ),
        ],
        # eval_status
        CheckTaskStatus.warning.value,
        # eval_value
        {
            "status.conditions.ready": True,
            "status.conditions.initialized": True,
            "status.conditions.containersready": True,
            "status.conditions.podscheduled": True,
            "status.conditions.unknowncondition": 'True',
            "status.phase": "Running"
        },
        # resource_name
        "akri-operator-6",
    ),
])
def test_process_pod_status(
    detail_level,
    eval_status,
    eval_value,
    mock_add_display_and_eval,
    mocked_check_manager,
    namespace,
    padding,
    pods,
    resource_name,
    target_service_pod,
):
    target_name = generate_random_string()

    process_pod_status(
        check_manager=mocked_check_manager,
        target=target_name,
        target_service_pod=target_service_pod,
        pods=pods,
        display_padding=padding,
        namespace=namespace,
        detail_level=detail_level,
    )

    if not pods:
        mock_add_display_and_eval.assert_any_call(
            check_manager=mocked_check_manager,
            target_name=target_name,
            display_text=f"{target_service_pod}* [yellow]not detected[/yellow].",
            eval_status=eval_status,
            eval_value=eval_value,
            resource_name=target_service_pod,
            namespace=namespace,
            padding=(0, 0, 0, padding)
        )

    else:
        assert mocked_check_manager.set_target_conditions.called or mocked_check_manager.add_target_conditions.called
        assert mocked_check_manager.add_display.called
        mocked_check_manager.add_target_eval.assert_any_call(
            target_name=target_name,
            namespace=namespace,
            status=eval_status,
            value=eval_value,
            resource_name=f"pod/{resource_name}"
        )
