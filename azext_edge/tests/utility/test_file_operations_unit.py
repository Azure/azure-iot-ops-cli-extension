# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import csv
import json
import yaml
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
                        if contents and not contents.startswith(header) and "vendor" not in entry.path:
                            files_missing_header.append(entry.path)

        _validate_directory(EXTENSION_ROOT)
        if files_missing_header:
            pytest.fail(
                "The following files are missing an encoding and license header, or it is improperly formatted:\n"
                "{}".format("\n".join(files_missing_header))
            )


@pytest.mark.parametrize("loader_return", ["", generate_random_string()])
@pytest.mark.parametrize("extension", ["json", "yml", "yaml", "csv", "whl"])
def test_deserialize_file_content(mocker, extension, loader_return):
    patched_loader = mocker.patch(
        "azext_edge.edge.util.file_operations._try_loading_as",
        return_value=loader_return
    )
    patched_reader = mocker.patch(
        "azext_edge.edge.util.file_operations.read_file_content",
        return_value=f"{generate_random_string()}\n{generate_random_string()}"
    )
    from azext_edge.edge.util import deserialize_file_content
    file_path = f"{generate_random_string()}.{extension}"

    if loader_return is None:
        with pytest.raises(FileOperationError):
            deserialize_file_content(file_path=file_path)
    else:
        result = deserialize_file_content(file_path=file_path)
        assert result == loader_return

    call_count = 0
    if extension == "json" or extension not in ["yml", "yaml", "csv"]:
        json_kwargs = patched_loader.call_args_list[call_count].kwargs
        assert json_kwargs["loader"] == json.loads
        assert json_kwargs["content"] == patched_reader.return_value
        assert json_kwargs["error_type"] == json.JSONDecodeError
        assert json_kwargs["raise_error"] == (extension == "json")
        call_count += 1

    multiple_calls = extension not in ["json", "yaml", "yml", "csv"] and (loader_return is None)
    if extension in ["yml", "yaml"] or multiple_calls:
        yaml_kwargs = patched_loader.call_args_list[call_count].kwargs
        assert yaml_kwargs["loader"] == yaml.safe_load
        assert yaml_kwargs["content"] == patched_reader.return_value
        assert yaml_kwargs["error_type"] == yaml.YAMLError
        assert yaml_kwargs["raise_error"] == (extension in ["yml", "yaml"])
        call_count += 1
    if extension == "csv" or multiple_calls:
        csv_kwargs = patched_loader.call_args_list[call_count].kwargs
        assert csv_kwargs["loader"] == csv.DictReader
        assert csv_kwargs["content"] == patched_reader.return_value.splitlines()
        assert csv_kwargs["error_type"] == csv.Error
        assert csv_kwargs["raise_error"] == (extension == "csv")


@pytest.mark.parametrize("dir_path", [
    None, generate_random_string(), os.path.join("~", generate_random_string())
])
@pytest.mark.parametrize("exists", [False, True])
def test_normalize_dir(dir_path, exists):
    from azext_edge.edge.util import normalize_dir

    if exists and dir_path:
        os.makedirs(os.path.abspath(os.path.expanduser(dir_path)), exist_ok=True)

    pure_dir_path = normalize_dir(dir_path)
    assert str(pure_dir_path) == os.path.abspath(os.path.expanduser(dir_path or "."))
    assert os.path.exists(str(pure_dir_path))

    if dir_path:
        os.rmdir(os.path.abspath(os.path.expanduser(dir_path)))


def test_read_file_content(tracked_files):
    from azext_edge.edge.util import read_file_content

    class TestScenario(NamedTuple):
        file_name: str
        file_size: int = 1024
        encoding: Optional[str] = None
        is_binary: bool = False

        def write_content(self) -> Union[bytes, str]:
            file_name = os.path.abspath(os.path.expanduser(self.file_name))
            mode = "w"
            if self.is_binary:
                mode += "b"
                random_data = os.urandom(self.file_size)
            else:
                random_data = generate_random_string(self.file_size)

            # pylint: disable-next=unspecified-encoding
            with open(file_name, mode=mode, encoding=self.encoding) as file:
                file.write(random_data)
            tracked_files.append(file_name)
            return random_data

    file_prefix = "azext_edge_util_test_data"

    test_scenarios: List[TestScenario] = []
    test_scenarios.append(TestScenario(f"{file_prefix}.bin", is_binary=True))
    test_scenarios.append(TestScenario(os.path.join("~", f"{file_prefix}.txt")))

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

    non_existant_path = "/some/path/that/doesnt/exist"
    with pytest.raises(FileOperationError, match=f"{non_existant_path} does not exist."):
        read_file_content(file_path=non_existant_path)

    directory_path = Path(__file__).parent.as_posix()
    with pytest.raises(FileOperationError, match=f"{directory_path} is not a file."):
        read_file_content(file_path=directory_path)


@pytest.mark.parametrize("return_value", [
    "",
    generate_random_string(),
    {generate_random_string(): generate_random_string()},
    [generate_random_string()]
])
@pytest.mark.parametrize("error", [None, FileOperationError])
@pytest.mark.parametrize("raise_error", [True, False])
def test_try_loading_as(mocker, error, raise_error, return_value):
    from azext_edge.edge.util.file_operations import _try_loading_as
    loader = mocker.Mock(return_value=return_value)
    if error:
        loader.side_effect = error(generate_random_string())
    content = generate_random_string()
    if error and raise_error:
        with pytest.raises(FileOperationError):
            _try_loading_as(
                loader=loader,
                content=content,
                error_type=FileOperationError,
                raise_error=raise_error
            )
    else:
        result = _try_loading_as(
            loader=loader,
            content=content,
            error_type=FileOperationError,
            raise_error=raise_error
        )
        assert result == (None if error else return_value)
    loader.assert_called_once_with(content)


@pytest.mark.parametrize("env_value", ["true", "y", "1", "false", "0", "no", "random", ""])
@pytest.mark.parametrize("flag_key", [generate_random_string()])
def test_is_env_flag_enabled(env_value: str, flag_key: str):
    from os import environ

    environ[flag_key] = env_value

    from azext_edge.edge.util import is_env_flag_enabled

    is_enabled = is_env_flag_enabled(flag_key)

    if env_value in ["true", "y", "1"]:
        assert is_enabled
        return

    assert not is_enabled

    del environ[flag_key]
