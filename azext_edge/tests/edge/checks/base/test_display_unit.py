# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azext_edge.edge.common import CheckTaskStatus
from azext_edge.edge.providers.check.common import ALL_NAMESPACES_TARGET

from ....generators import generate_random_string


@pytest.mark.parametrize("resource_name", [None, generate_random_string()])
@pytest.mark.parametrize("namespace", [ALL_NAMESPACES_TARGET, generate_random_string()])
@pytest.mark.parametrize("padding", [(0, 0, 0, 8), (3, 5, 2, 9)])
def test_add_display_and_eval(mocked_check_manager, resource_name, namespace, padding):
    from azext_edge.edge.providers.check.base import add_display_and_eval
    target_name = generate_random_string()
    display_text = generate_random_string()
    eval_status = generate_random_string()
    eval_value = generate_random_string()
    add_display_and_eval(
        check_manager=mocked_check_manager,
        target_name=target_name,
        display_text=display_text,
        eval_status=eval_status,
        eval_value=eval_value,
        resource_name=resource_name,
        namespace=namespace,
        padding=padding
    )
    kwargs = mocked_check_manager.add_display.call_args.kwargs
    assert kwargs["target_name"] == target_name
    assert kwargs["namespace"] == namespace
    assert kwargs["display"].renderable == display_text
    assert (
        kwargs["display"].top,
        kwargs["display"].right,
        kwargs["display"].bottom,
        kwargs["display"].left
    ) == padding

    mocked_check_manager.add_target_eval.assert_called_once_with(
        target_name=target_name,
        namespace=namespace,
        status=eval_status,
        value=eval_value,
        resource_name=resource_name
    )


@pytest.mark.parametrize("key", ["discoveryError", "discovery", "error", 0])
@pytest.mark.parametrize("value", ["Null", "", "None", "NoError", "Everything is ok~", 100])
def test_process_value_color(mocked_check_manager, key, value):
    from azext_edge.edge.providers.check.base import process_value_color
    target_name = generate_random_string()
    result = process_value_color(
        check_manager=mocked_check_manager, target_name=target_name, key=key, value=value
    )
    if not value:
        value = "N/A"
    assert str(value) in result

    if all([
        "error" in str(key).lower(),
        str(value).lower() not in ["null", "n/a", "none", "noerror"]
    ]):
        assert result.startswith("[red]")
        mocked_check_manager.set_target_status.assert_called_once_with(
            target_name=target_name,
            status=CheckTaskStatus.error.value
        )
    else:
        assert result.startswith("[cyan]")
