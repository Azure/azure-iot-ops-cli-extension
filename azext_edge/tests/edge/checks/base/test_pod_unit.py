# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest

from azext_edge.edge.common import CheckTaskStatus, PodState
from azext_edge.edge.providers.check.base import (
    decorate_pod_phase,
    evaluate_detailed_pod_health,
)
from azext_edge.edge.providers.check.base.pod import (
    evaluate_pod_health,
    process_pods_status,
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
@pytest.mark.parametrize("namespace", [ALL_NAMESPACES_TARGET, generate_random_string()])
@pytest.mark.parametrize("padding", [4])
@pytest.mark.parametrize(
    "pods",
    [
        [],
        [generate_pod_stub(name="lnm-operator-1", phase="Running")],
        [generate_pod_stub(name="lnm-operator-1", phase="Pending")],
        [generate_pod_stub(name="lnm-operator-1", phase="Failed")],
        [
            generate_pod_stub(
                name="lnm-operator-1",
                phase="Running",
            ),
            generate_pod_stub(
                name="lnm-operator-2",
                phase="Pending",
            ),
        ],
        [
            generate_pod_stub(
                name="lnm-operator-1",
                phase="Running",
            ),
            generate_pod_stub(
                name="lnm-operator-3",
                phase="Failed",
            ),
        ],
    ]
)
def test_evaluate_pod_health(
    mocker,
    mock_process_pods_status,
    mocked_check_manager,
    namespace,
    padding,
    pods,
    target_service_pod,
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
    )

    mocked_check_manager.add_target_conditions.assert_called_once_with(
        target_name=target_service_pod,
        namespace=namespace,
        conditions=[f"pod/{target_service_pod}.status.phase"]
    )

    mock_process_pods_status.assert_called_once_with(
        check_manager=mocked_check_manager,
        namespace=namespace,
        target=target_service_pod,
        target_service_pod=f"pod/{target_service_pod}",
        pods=pods,
        display_padding=padding
    )


@pytest.mark.parametrize("target_service_pod", [generate_random_string()])
@pytest.mark.parametrize("namespace", [ALL_NAMESPACES_TARGET, generate_random_string()])
@pytest.mark.parametrize("padding", [4])
@pytest.mark.parametrize(
    "pods",
    [
        [],
        [generate_pod_stub(name="lnm-operator-1", phase="Running")],
        [generate_pod_stub(name="lnm-operator-1", phase="Pending")],
        [generate_pod_stub(name="lnm-operator-1", phase="Failed")],
        [
            generate_pod_stub(
                name="lnm-operator-1",
                phase="Running",
            ),
            generate_pod_stub(
                name="lnm-operator-2",
                phase="Pending",
            ),
        ],
        [
            generate_pod_stub(
                name="lnm-operator-1",
                phase="Running",
            ),
            generate_pod_stub(
                name="lnm-operator-3",
                phase="Failed",
            ),
        ],
    ]
)
def test_process_pods_status(
    mock_add_display_and_eval,
    mocked_check_manager,
    namespace,
    padding,
    pods,
    target_service_pod,
):
    process_pods_status(
        check_manager=mocked_check_manager,
        namespace=namespace,
        target=target_service_pod,
        target_service_pod=target_service_pod,
        pods=pods,
        display_padding=padding,
    )

    if not pods:
        mock_add_display_and_eval.assert_called_once_with(
            check_manager=mocked_check_manager,
            target_name=target_service_pod,
            display_text=f"{target_service_pod}* [yellow]not detected[/yellow].",
            eval_status=CheckTaskStatus.warning.value,
            eval_value=None,
            resource_name=target_service_pod,
            namespace=namespace,
            padding=(0, 0, 0, padding)
        )

    else:
        for pod in pods:
            pod_dict = pod.to_dict()
            pod_name = pod_dict["metadata"]["name"]
            pod_phase = pod_dict.get("status", {}).get("phase")
            pod_phase_deco, status = decorate_pod_phase(pod_phase)
            resource_name = f"pod/{pod_name}"
            mock_add_display_and_eval.assert_any_call(
                check_manager=mocked_check_manager,
                target_name=target_service_pod,
                display_text=f"Pod {{[bright_blue]{pod_name}[/bright_blue]}} in phase {{{pod_phase_deco}}}.",
                eval_status=status,
                eval_value={"name": pod_name, "status.phase": pod_phase},
                resource_name=resource_name,
                namespace=namespace,
                padding=(0, 0, 0, padding)
            )


@pytest.mark.parametrize("target_service_pod", [generate_random_string()])
@pytest.mark.parametrize("namespace", [ALL_NAMESPACES_TARGET, generate_random_string()])
@pytest.mark.parametrize("padding", [4])
@pytest.mark.parametrize("detail_level", ResourceOutputDetailLevel.list())
@pytest.mark.parametrize("pod, eval_status, eval_value, resource_name, conditions", [
    (
        # pod
        None,
        # eval_status
        CheckTaskStatus.warning.value,
        # eval_value
        None,
        # resource_name
        "",
        # conditions
        []
    ),
    (
        # pod
        generate_pod_stub(
            name="lnm-operator-1",
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
        # eval_status
        CheckTaskStatus.success.value,
        # eval_value
        {"name": "lnm-operator-1", "status.phase": "Running"},
        # resource_name
        "lnm-operator-1",
        # conditions
        [
            {
                "type": "Ready",
                "status": "True",
                "status_text": "Pod Readiness: [green]True[/green]",
                "eval_status": CheckTaskStatus.success.value
            },
            {
                "type": "Initialized",
                "status": "True",
                "status_text": "Pod Initialized: [green]True[/green]",
                "eval_status": CheckTaskStatus.success.value
            },
            {
                "type": "ContainersReady",
                "status": "True",
                "status_text": "Containers Readiness: [green]True[/green]",
                "eval_status": CheckTaskStatus.success.value
            },
            {
                "type": "PodScheduled",
                "status": "True",
                "status_text": "Pod Scheduled: [green]True[/green]",
                "eval_status": CheckTaskStatus.success.value
            },
        ]
    ),
    (
        # pod
        generate_pod_stub(
            name="lnm-operator-2",
            phase="Pending",
            conditions=[
                {
                    "type": "PodReadyToStartContainers",
                    "status": "True",
                }
            ]
        ),
        # eval_status
        CheckTaskStatus.warning.value,
        # eval_value
        {"name": "lnm-operator-2", "status.phase": "Pending"},
        # resource_name
        "lnm-operator-2",
        # conditions
        [
            {
                "type": "PodReadyToStartContainers",
                "status": "True",
                "status_text": "Pod Ready To Start Containers: [green]True[/green]",
                "eval_status": CheckTaskStatus.success.value
            }
        ]
    ),
    (
        # pod
        generate_pod_stub(
            name="lnm-operator-3",
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
        # eval_status
        CheckTaskStatus.success.value,
        # eval_value
        {"name": "lnm-operator-3", "status.phase": "Running"},
        # resource_name
        "lnm-operator-3",
        # conditions
        [
            {
                "type": "Ready",
                "status": "False",
                "status_text": "Pod Readiness: [red]False[/red]",
                "eval_status": CheckTaskStatus.error.value
            },
            {
                "type": "Initialized",
                "status": "False",
                "status_text": "Pod Initialized: [red]False[/red]",
                "eval_status": CheckTaskStatus.error.value
            },
            {
                "type": "ContainersReady",
                "status": "False",
                "status_text": "Containers Readiness: [red]False[/red]",
                "eval_status": CheckTaskStatus.error.value
            },
            {
                "type": "PodScheduled",
                "status": "False",
                "status_text": "Pod Scheduled: [red]False[/red]",
                "eval_status": CheckTaskStatus.error.value
            },
            {
                "type": "PodReadyToStartContainers",
                "status": "False",
                "status_text": "Pod Ready To Start Containers: [red]False[/red]",
                "eval_status": CheckTaskStatus.error.value
            }
        ]
    ),
    (
        # pod
        generate_pod_stub(
            name="lnm-operator-4",
            phase="Pending",
            conditions=[
                {
                    "type": "Ready",
                    "status": "True",
                },
            ]
        ),
        # eval_status
        CheckTaskStatus.warning.value,
        # eval_value
        {"name": "lnm-operator-4", "status.phase": "Pending"},
        # resource_name
        "lnm-operator-4",
        # conditions
        [
            {
                "type": "Ready",
                "status": "True",
                "status_text": "Pod Readiness: [green]True[/green]",
                "eval_status": CheckTaskStatus.success.value
            }
        ]
    ),
    (
        # pod
        generate_pod_stub(
            name="lnm-operator-5",
            phase="Failed",
            conditions=None
        ),
        # eval_status
        CheckTaskStatus.error.value,
        # eval_value
        {"name": "lnm-operator-5", "status.phase": "Failed"},
        # resource_name
        "lnm-operator-5",
        # conditions
        None
    )
])
def test_evaluate_detailed_pod_health(
    conditions,
    detail_level,
    eval_status,
    eval_value,
    mock_add_display_and_eval,
    mocked_check_manager,
    namespace,
    padding,
    pod,
    resource_name,
    target_service_pod,
):
    target_name = generate_random_string()

    evaluate_detailed_pod_health(
        check_manager=mocked_check_manager,
        target=target_name,
        target_service_pod=target_service_pod,
        pod=pod,
        display_padding=padding,
        namespace=namespace,
        detail_level=detail_level,
    )

    if not pod:
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
        mocked_check_manager.add_target_eval.assert_any_call(
            target_name=target_name,
            namespace=namespace,
            status=eval_status,
            value=eval_value,
            resource_name=f"pod/{resource_name}"
        )

        if not conditions:
            return

        for condition in conditions:
            condition_status = True if condition.get("status") == "True" else False
            mock_add_display_and_eval.assert_any_call(
                check_manager=mocked_check_manager,
                target_name=target_name,
                display_text=condition["status_text"],
                eval_status=condition["eval_status"],
                eval_value={"name": resource_name, f"status.conditions.{condition['type'].lower()}": condition_status},
                resource_name=f"pod/{resource_name}",
                namespace=namespace,
                padding=(0, 0, 0, padding + 8)
            )

            if detail_level > ResourceOutputDetailLevel.summary.value:
                mocked_check_manager.add_display.assert_called()
