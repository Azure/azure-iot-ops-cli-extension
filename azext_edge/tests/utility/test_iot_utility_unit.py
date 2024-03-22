# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
from typing import List, NamedTuple, Optional, Union
from pathlib import Path

import pytest
from azure.cli.core.azclierror import FileOperationError

from ..generators import generate_random_string


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
                invalid_directories.append("Directory: '{}' missing __init__.py".format(directory))

        if invalid_directories:
            pytest.fail(", ".join(invalid_directories))


class TestFileHeaders(object):
    def test_file_headers(self):
        from azext_edge.constants import EXTENSION_ROOT

        header = """# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------"""

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


def test_read_file_content():
    from azext_edge.edge.util import read_file_content

    class TestScenario(NamedTuple):
        file_name: str
        file_size: int = 1024
        encoding: Optional[str] = None
        is_binary: bool = False

        def write_content(self) -> Union[bytes, str]:
            mode = "w"
            if self.is_binary:
                mode += "b"
                random_data = os.urandom(self.file_size)
            else:
                random_data = generate_random_string(self.file_size)

            # pylint: disable-next=unspecified-encoding
            with open(self.file_name, mode=mode, encoding=self.encoding) as file:
                file.write(random_data)
            return random_data

        def delete_content(self):
            os.remove(self.file_name)

    file_prefix = "azext_edge_util_test_data"

    test_scenarios: List[TestScenario] = []
    test_scenarios.append(TestScenario(f"{file_prefix}.bin", is_binary=True))

    for encoding_tuple in [
        ("utf-8-sig", "utf8sig"),
        ("utf-8", "utf8"),
    ]:
        file_encoding, file_suffix = encoding_tuple
        test_scenarios.append(TestScenario(f"{file_prefix}.{file_suffix}", encoding=file_encoding))

    for scenario in test_scenarios:
        expected_content = scenario.write_content()

        if scenario.is_binary:
            with pytest.raises(FileOperationError, match="Failed to decode file azext_edge_util_test_data.bin"):
                read_file_content(file_path=scenario.file_name, read_as_binary=False)

        file_content = read_file_content(file_path=scenario.file_name, read_as_binary=scenario.is_binary)
        assert file_content == expected_content
        scenario.delete_content()

    non_existant_path = "/some/path/that/doesnt/exist"
    with pytest.raises(FileOperationError, match=f"{non_existant_path} does not exist."):
        read_file_content(file_path=non_existant_path)

    directory_path = Path(__file__).parent.as_posix()
    with pytest.raises(FileOperationError, match=f"{directory_path} is not a file."):
        read_file_content(file_path=directory_path)
