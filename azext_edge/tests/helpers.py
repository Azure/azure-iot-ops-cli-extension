# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Dict
from azure.cli.core.azclierror import CLIInternalError



def parse_rest_command(rest_command: str) -> Dict[str, str]:
    """Simple az rest command parsing."""
    assert rest_command.startswith("rest")
    rest_list = rest_command.split("--")[1:]
    result = {}
    for rest_input in rest_list:
        key, value = rest_input.split(maxsplit=1)
        result[key] = value.strip()
    return result


class CommandRunner():
    def __init__(self):
        from os import fdopen
        self.stdin = fdopen(0)

    def run(self, command: str, shell_mode: bool = True, expect_failure: bool = False):
        """
        Wrapper function for run_host_command used for testing.
        Parameter `expect_failure` determines if an error will be raised for the command result.
        The output is converted to non-binary text and loaded as a json if possible.
        """
        from subprocess import run, PIPE

        result = run(command, check=False, shell=shell_mode, stdin=self.stdin, stdout=PIPE, stderr=PIPE, text=True)
        if expect_failure and result.returncode == 0:
            raise CLIInternalError(f"Command `{command}` did not fail as expected.")
        elif not expect_failure and result.returncode != 0:
            raise CLIInternalError(result.stderr)

        if result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return result.stdout

    def close_stdin(self):
        self.stdin.close()
