# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
import pytest

ENV_VAR = "AIO_SUPPORT_BUNDLE_INT_TEST"


@pytest.fixture(scope="session")
def bundle_setup():
    """Sets the env variable so bundle names can be customized for integration tests."""
    os.environ[ENV_VAR] = "true"
    yield
    del os.environ[ENV_VAR]
