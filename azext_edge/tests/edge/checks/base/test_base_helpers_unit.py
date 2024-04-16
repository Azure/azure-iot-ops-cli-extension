# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from azext_edge.edge.common import CheckTaskStatus

from ....generators import generate_random_string


@pytest.fixture
def mock_check_manager(mocker):
    mocked_manager = mocker.patch("azext_edge.edge.providers.check.base.CheckManager", autospec=True)
    yield mocked_manager


@pytest.mark.parametrize("key", ["discoveryError", "discovery", "error", 0])
@pytest.mark.parametrize("value", ["Null", "", "None", "NoError", "Everything is ok~", 100])
def test_process_value_color(mock_check_manager, key, value):
    from azext_edge.edge.providers.check.base import process_value_color
    target_name = generate_random_string()
    result = process_value_color(
        check_manager=mock_check_manager, target_name=target_name, key=key, value=value
    )
    if not value:
        value = "N/A"
    assert str(value) in result

    if all([
        "error" in str(key).lower(),
        str(value).lower() not in ["null", "n/a", "none", "noerror"]
    ]):
        assert result.startswith("[red]")
        mock_check_manager.set_target_status.assert_called_once_with(
            target_name=target_name,
            status=CheckTaskStatus.error.value
        )
    else:
        assert result.startswith("[cyan]")
