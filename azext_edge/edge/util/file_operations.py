# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import csv
import json
import yaml
import os
from pathlib import PurePath
from typing import Any, Callable, List, Optional, Union
from azure.cli.core.azclierror import FileOperationError
from knack.log import get_logger

logger = get_logger(__name__)


# TODO: unit test
def dump_content_to_file(
    content: List[dict],
    file_name: str,
    extension: str,
    fieldnames: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    replace: bool = False,
) -> PurePath:
    output_dir = normalize_dir(output_dir)
    file_path = os.path.join(output_dir, f"{file_name}.{extension}")
    if os.path.exists(file_path):
        if not replace:
            raise FileExistsError(f"File {file_path} already exists. Please choose another file name or add replace.")
        logger.warning(f"The file {file_path} will be overwritten.")
    if extension.endswith("csv"):
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            if not fieldnames:
                fieldnames = content[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(content)
        return file_path

    # These let you dump to a string before writing to file
    if extension == "json":
        content = json.dumps(content, indent=2)
    elif extension in ["yaml", "yml"]:
        content = yaml.dump(content)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


def normalize_dir(dir_path: Optional[str] = None) -> PurePath:
    if not dir_path:
        dir_path = "."
    if "~" in dir_path:
        dir_path = os.path.expanduser(dir_path)
    dir_path = os.path.abspath(dir_path)
    dir_pure_path = PurePath(dir_path)
    if not os.path.exists(str(dir_pure_path)):
        os.makedirs(dir_pure_path, exist_ok=True)

    return dir_pure_path


def read_file_content(file_path: str, read_as_binary: bool = False) -> Union[bytes, str]:
    from pathlib import Path

    logger.debug("Processing %s", file_path)
    pure_path = Path(os.path.abspath(os.path.expanduser(file_path)))

    if not pure_path.exists():
        raise FileOperationError(f"{file_path} does not exist.")

    if not pure_path.is_file():
        raise FileOperationError(f"{file_path} is not a file.")

    if read_as_binary:
        logger.debug("Reading %s as binary", file_path)
        return pure_path.read_bytes()

    # Try with 'utf-8-sig' first, so that BOM in WinOS won't cause trouble.
    for encoding in ["utf-8-sig", "utf-8"]:
        try:
            logger.debug("Reading %s as %s", file_path, encoding)
            return pure_path.read_text(encoding=encoding)
        except (UnicodeError, UnicodeDecodeError):
            pass

    raise FileOperationError(f"Failed to decode file {file_path}.")


def deserialize_file_content(file_path: str) -> Any:
    extension = file_path.split(".")[-1]
    valid_extension = extension in ["json", "yaml", "yml", "csv"]
    content = read_file_content(file_path)
    result = None
    if not valid_extension or extension == "json":
        # will always be a list or dict
        result = _try_loading_as(
            loader=json.loads, content=content, error_type=json.JSONDecodeError, raise_error=valid_extension
        )
    if (not result and not valid_extension) or extension in ["yaml", "yml"]:
        # can be list, dict, str, int, bool, none
        result = _try_loading_as(
            loader=yaml.safe_load, content=content, error_type=yaml.YAMLError, raise_error=valid_extension
        )
    if (not result and not valid_extension) or extension == "csv":
        # iterrable object so lets cast to list
        result = _try_loading_as(
            loader=csv.DictReader, content=content.splitlines(), error_type=csv.Error, raise_error=valid_extension
        )
    if result is not None or valid_extension:
        return result
    raise FileOperationError(f"File contents for {file_path} cannot be read.")


def validate_file_extension(file_name: str, expected_exts: List[str]) -> str:
    ext = os.path.splitext(file_name)[1]
    lowercased_exts = [ext.lower() for ext in expected_exts]
    if ext.lower() not in lowercased_exts:
        exts_text = ", ".join(expected_exts)
        raise ValueError(
            f"Invalid file extension found for {file_name}, only {exts_text} file extensions are supported."
        )

    return ext


def _try_loading_as(loader: Callable, content: str, error_type: Exception, raise_error: bool = True) -> Optional[Any]:
    try:
        return loader(content)
    except error_type as e:
        if raise_error:
            raise FileOperationError(e)
