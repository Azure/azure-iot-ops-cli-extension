# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from unittest.mock import ANY

from azext_edge.edge.common import CheckTaskStatus, PodState
from azext_edge.edge.providers.check.base import (
    evaluate_pod_health,
)
from azext_edge.edge.providers.check.base.pod import _process_pod_status, decorate_pod_phase
from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET, ResourceOutputDetailLevel
from azext_edge.tests.edge.checks.conftest import generate_pod_stub
from ....generators import generate_random_string


@pytest.mark.parametrize(
    "phase, expected",
    [
        ("Running", ("[green]Running[/green]", PodState.map_to_status("Running").value)),
        ("Pending", ("[yellow]Pending[/yellow]", PodState.map_to_status("Pending").value)),
        ("Failed", ("[red]Failed[/red]", PodState.map_to_status("Failed").value)),
        ("Succeeded", ("[green]Succeeded[/green]", PodState.map_to_status("Succeeded").value)),
        ("Unknown", ("[yellow]Unknown[/yellow]", PodState.map_to_status("Unknown").value)),
    ],
)
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
    ],
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
    target_service_pod = generate_random_string()
    namespace = generate_random_string()
    padding = 4

    evaluate_pod_health(
        check_manager=mocked_check_manager,
        namespace=namespace,
        target=target_service_pod,
        padding=padding,
        pods=pods,
        detail_level=detail_level,
    )

    call_args_list = mock_process_pod_status.call_args_list
    for call_args, pod in zip(call_args_list, pods):
        kwargs = call_args.kwargs
        assert kwargs["check_manager"] == mocked_check_manager
        assert kwargs["namespace"] == namespace
        assert kwargs["target"] == target_service_pod
        assert kwargs["pod"] == pod
        assert kwargs["detail_level"] == detail_level


@pytest.mark.parametrize("namespace", [ALL_NAMESPACES_TARGET, generate_random_string()])
@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize(
    "pod, eval_status, eval_value, resource_name, expected_display_texts",
    [
        (
            # pod
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
                ],
            ),
            # eval_status
            CheckTaskStatus.success.value,
            # eval_value
            {
                "status.conditions.ready": True,
                "status.conditions.initialized": True,
                "status.conditions.containersready": True,
                "status.conditions.podscheduled": True,
                "status.phase": "Running",
            },
            # resource_name
            "akri-operator-1",
            # expected_display_texts
            ["[green]:heavy_check_mark:[/green]", "Pod {[bright_blue]akri-operator-1[/bright_blue]}"],
        ),
        (
            # pod
            generate_pod_stub(
                name="mq-operator-2",
                phase="Pending",
                conditions=[
                    {
                        "type": "PodReadyToStartContainers",
                        "status": "True",
                    }
                ],
            ),
            # eval_status
            CheckTaskStatus.warning.value,
            # eval_value
            {"status.conditions.podreadytostartcontainers": True, "status.phase": "Pending"},
            # resource_name
            "mq-operator-2",
            # expected_display_texts
            ["[yellow]:warning:[/yellow]", "Pod {[bright_blue]mq-operator-2[/bright_blue]}"],
        ),
        (
            # pod
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
                    },
                ],
            ),
            # eval_status
            CheckTaskStatus.error.value,
            # eval_value
            {
                "status.conditions.ready": False,
                "status.conditions.initialized": False,
                "status.conditions.containersready": False,
                "status.conditions.podscheduled": False,
                "status.conditions.podreadytostartcontainers": False,
                "status.phase": "Running",
            },
            # resource_name
            "aio-operator-3",
            # expected_display_texts
            ["[red]:stop_sign:[/red]", "Pod {[bright_blue]aio-operator-3[/bright_blue]}"],
        ),
        (
            # pod
            generate_pod_stub(
                name="opcua-operator-4",
                phase="Pending",
                conditions=[
                    {
                        "type": "Ready",
                        "status": "True",
                    },
                ],
            ),
            # eval_status
            CheckTaskStatus.warning.value,
            # eval_value
            {"status.conditions.ready": True, "status.phase": "Pending"},
            # resource_name
            "opcua-operator-4",
            # expected_display_texts
            ["[yellow]:warning:[/yellow]", "Pod {[bright_blue]opcua-operator-4[/bright_blue]}"],
        ),
        (
            # pod
            generate_pod_stub(name="mq-operator-5", phase="Failed", conditions=None),
            # eval_status
            CheckTaskStatus.error.value,
            # eval_value
            {"status.phase": "Failed"},
            # resource_name
            "mq-operator-5",
            # expected_display_texts
            ["[red]:stop_sign:[/red]", "Pod {[bright_blue]mq-operator-5[/bright_blue]}"],
        ),
        (
            # pod
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
                    },
                ],
            ),
            # eval_status
            CheckTaskStatus.warning.value,
            # eval_value
            {
                "status.conditions.ready": True,
                "status.conditions.initialized": True,
                "status.conditions.containersready": True,
                "status.conditions.podscheduled": True,
                "status.conditions.unknowncondition": "True",
                "status.phase": "Running",
            },
            # resource_name
            "akri-operator-6",
            # expected_display_texts
            ["[yellow]:warning:[/yellow]", "Pod {[bright_blue]akri-operator-6[/bright_blue]}"],
        ),
        (
            # pod
            generate_pod_stub(
                name="akri-operator-7",
                phase="Starting",
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
                        "status": "False",
                    },
                ],
            ),
            # eval_status
            CheckTaskStatus.error.value,
            # eval_value
            {
                "status.conditions.ready": True,
                "status.conditions.initialized": True,
                "status.conditions.containersready": True,
                "status.conditions.podscheduled": False,
                "status.phase": "Starting",
            },
            # resource_name
            "akri-operator-7",
            # expected_display_texts
            ["[red]:stop_sign:[/red]", "Pod {[bright_blue]akri-operator-7[/bright_blue]}"],
        ),
    ],
)
def test_process_pod_status(
    mocker,
    detail_level,
    eval_status,
    eval_value,
    mocked_check_manager,
    namespace,
    pod,
    resource_name,
    expected_display_texts,
):
    target_name = generate_random_string()

    (display_texts, status) = _process_pod_status(
        check_manager=mocked_check_manager,
        target=target_name,
        pod=pod,
        namespace=namespace,
        detail_level=detail_level,
    )

    assert mocked_check_manager.set_target_conditions.called or mocked_check_manager.add_target_conditions.called
    mocked_check_manager.add_target_eval.assert_any_call(
        target_name=target_name,
        namespace=namespace,
        status=eval_status,
        value=eval_value,
        resource_name=f"pod/{resource_name}",
    )

    if detail_level == ResourceOutputDetailLevel.summary.value:
        assert display_texts == expected_display_texts
    assert status == eval_status
