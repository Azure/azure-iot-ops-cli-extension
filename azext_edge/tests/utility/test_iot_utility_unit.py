# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os
from unittest import mock

import pytest
from azure.cli.core.extension import get_extension_path
from knack.util import CLIError

from azext_edge.common.utility import validate_min_python_version
from azext_edge.constants import EXTENSION_NAME


class TestMinPython(object):
    @pytest.mark.parametrize("pymajor, pyminor", [(3, 6), (3, 4), (2, 7)])
    def test_min_python(self, pymajor, pyminor):
        with mock.patch("azext_edge.common.utility.sys.version_info") as version_mock:
            version_mock.major = pymajor
            version_mock.minor = pyminor

            assert validate_min_python_version(2, 7)

    @pytest.mark.parametrize(
        "pymajor, pyminor, exception",
        [(3, 6, SystemExit), (3, 4, SystemExit), (2, 7, SystemExit)],
    )
    def test_min_python_error(self, pymajor, pyminor, exception):
        with mock.patch("azext_edge.common.utility.sys.version_info") as version_mock:
            version_mock.major = 2
            version_mock.minor = 6

            with pytest.raises(exception):
                validate_min_python_version(pymajor, pyminor)


class TestCliInit(object):
    def test_package_init(self):
        from azext_edge.constants import EXTENSION_ROOT

        tests_root = "tests"
        directory_structure = {}

        def _validate_directory(path):
            for entry in os.scandir(path):
                if entry.is_dir(follow_symlinks=False) and all(
                    [not entry.name.startswith("__"), tests_root not in entry.path]
                ):
                    directory_structure[entry.path] = None
                    _validate_directory(entry.path)
                else:
                    if entry.path.endswith("__init__.py"):
                        directory_structure[os.path.dirname(entry.path)] = entry.path

        _validate_directory(EXTENSION_ROOT)

        invalid_directories = []
        for directory in directory_structure:
            if directory_structure[directory] is None:
                invalid_directories.append(
                    "Directory: '{}' missing __init__.py".format(directory)
                )

        if invalid_directories:
            pytest.fail(", ".join(invalid_directories))


class TestFileHeaders(object):
    def test_file_headers(self):
        from azext_edge.constants import EXTENSION_ROOT

        header = """# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------"""

        files_missing_header = []
        sdk_root = "sdk"

        def _validate_directory(path):
            for entry in os.scandir(path):
                if entry.is_dir(follow_symlinks=False) and sdk_root not in entry.path:
                    _validate_directory(entry.path)
                else:
                    if entry.is_file() and entry.path.endswith(".py"):
                        contents = None
                        with open(entry.path, "rt", encoding="utf-8") as f:
                            contents = f.read()
                        if contents and not contents.startswith(header):
                            files_missing_header.append(entry.path)

        _validate_directory(EXTENSION_ROOT)
        if files_missing_header:
            pytest.fail(
                "The following files are missing an encoding and license header, or it is improperly formatted:\n"
                "{}".format("\n".join(files_missing_header))
            )
