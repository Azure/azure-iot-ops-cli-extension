# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import secrets
import string
from typing import List, Union
from uuid import uuid4


def generate_generic_id() -> str:
    return str(uuid4()).replace("-", "")


def generate_names(prefix: str = "", count: int = 1, max_length: int = 48) -> Union[str, List[str]]:
    """
    Generic name generator that returns a list of names. If only one
    name is generated, returns only the name as a string.
    """
    names = [(prefix + generate_generic_id())[:max_length] for _ in range(count)]
    return names[0] if count == 1 else names


def get_zeroed_subscription() -> str:
    return "00000000-0000-0000-0000-000000000000"


def generate_random_string(size: int):
    valid_sequence = string.ascii_lowercase + string.ascii_uppercase + string.digits
    return "".join(secrets.choice(valid_sequence) for _ in range(size))
