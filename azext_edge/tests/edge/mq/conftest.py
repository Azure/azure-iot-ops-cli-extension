# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest


@pytest.fixture
def mocked_zipfile(mocker):
    patched = mocker.patch("zipfile.ZipFile", autospec=True)
    yield patched
