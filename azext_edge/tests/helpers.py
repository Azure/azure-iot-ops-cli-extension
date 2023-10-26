# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Dict


def parse_rest_command(rest_command: str) -> Dict[str, str]:
    """Simple az rest command parsing."""
    assert rest_command.startswith("rest")
    rest_list = rest_command.split("--")[1:]
    result = {}
    for rest_input in rest_list:
        key, value = rest_input.split(maxsplit=1)
        result[key] = value.strip()
    return result
