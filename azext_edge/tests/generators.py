# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import List, Union
from uuid import uuid4


def generate_generic_id() -> str:
    return str(uuid4()).replace("-", "")


def generate_names(prefix: str = "", count: int = 1, max_length: int = 48) -> Union[str, List[str]]:
    """
    Generic name generator that returns a list of names. If only one
    name is generated, returns only the name as a string.
    """
    names = [
        (prefix + generate_generic_id())[:max_length] for _ in range(count)
    ]
    return names[0] if count == 1 else names
