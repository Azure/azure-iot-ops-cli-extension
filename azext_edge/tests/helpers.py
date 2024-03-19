# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import os
import shutil
from knack.log import get_logger
from typing import Dict
from azure.cli.core.azclierror import CLIInternalError

logger = get_logger(__name__)


def parse_rest_command(rest_command: str) -> Dict[str, str]:
    """Simple az rest command parsing."""
    assert rest_command.startswith("rest")
    rest_list = rest_command.split("--")[1:]
    result = {}
    for rest_input in rest_list:
        key, value = rest_input.split(maxsplit=1)
        result[key] = value.strip()
    return result


def remove_file_or_folder(file_path):
    if os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            logger.error(f"Failed to remove file: {file_path}. {e}")
    if os.path.isdir(file_path):
        try:
            shutil.rmtree(file_path)
        except OSError as e:
            logger.error(f"Failed to remove directory: {file_path}. {e}")


def run(command: str, shell_mode: bool = True, expect_failure: bool = False):
    """
    Wrapper function for run_host_command used for testing.
    Parameter `expect_failure` determines if an error will be raised for the command result.
    The output is converted to non-binary text and loaded as a json if possible.
    """
    import subprocess

    result = subprocess.run(command, check=False, shell=shell_mode, text=True, capture_output=True)
    if expect_failure and result.returncode == 0:
        raise CLIInternalError(f"Command `{command}` did not fail as expected.")
    elif not expect_failure and result.returncode != 0:
        raise CLIInternalError(result.stderr)

    if result.stdout:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout
