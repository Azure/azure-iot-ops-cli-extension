# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import csv
import json
import yaml
import os
from typing import List, Optional
from azure.cli.core.azclierror import FileOperationError
from knack.log import get_logger

logger = get_logger(__name__)


def convert_file_content_to_json(file_path: str):
    extension = file_path.split(".")[-1]
    content = read_file_content(file_path)
    if extension == "json":
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise FileOperationError(f"Invalid JSON syntax: {e}")
    elif extension == "yaml":
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise FileOperationError(f"Invalid YAML syntax: {e}")
    elif extension == "csv":
        try:
            with open(file_path, "r") as f:
                reader = csv.DictReader(f)
                result = [row for row in reader]
            return result
        except csv.Error as e:
            raise FileOperationError(f"Invalid CSV syntax: {e}")
    raise FileOperationError(f"Detected {extension} extension is not supported.")


def dump_content_to_file(
    content: List[dict],
    file_name: str,
    extension: str,
    fieldnames: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
    replace: bool = False
):
    if not output_dir:
        output_dir = "."
    file_path = os.path.join(output_dir, f"{file_name}.{extension}")
    if os.path.exists(file_path):
        if not replace:
            raise FileExistsError(f"File {file_path} already exists. Please choose another file name or add replace.")
        logger.warning(f"The file {file_path} will be overwritten.")
    if extension.endswith("csv"):
        with open(file_path, "w", newline="") as f:
            if not fieldnames:
                fieldnames = content[0].keys()
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(content)
        return

    # These let you dump to a string before writing to file
    if extension == "json":
        content = json.dumps(content, indent=2)
    elif extension == "yaml":
        content = yaml.dump(content)
    with open(file_path, "w") as f:
        f.write(content)


def read_file_content(file_path: str, read_as_binary: bool = False):
    from codecs import open as codecs_open

    if read_as_binary:
        with open(file_path, "rb") as input_file:
            logger.debug("Attempting to read file %s as binary", file_path)
            return input_file.read()

    # Note, always put 'utf-8-sig' first, so that BOM in WinOS won't cause trouble.
    for encoding in ["utf-8-sig", "utf-8", "utf-16", "utf-16le", "utf-16be"]:
        try:
            with codecs_open(file_path, encoding=encoding) as f:
                logger.debug("Attempting to read file %s as %s", file_path, encoding)
                return f.read()
        except (UnicodeError, UnicodeDecodeError):
            pass

    raise FileOperationError("Failed to decode file {} - unknown decoding".format(file_path))
