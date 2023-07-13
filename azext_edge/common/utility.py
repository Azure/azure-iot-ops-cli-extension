# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
utility: Defines common utility functions and components.

"""

import os
from typing import List, Dict
from knack.log import get_logger


logger = get_logger(__name__)


def scantree(path):
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path)
        else:
            yield entry


def assemble_nargs_to_dict(hash_list: List[str]) -> Dict[str, str]:
    result = {}
    if not hash_list:
        return result
    for hash in hash_list:
        if "=" not in hash:
            logger.warning(
                "Skipping processing of '%s', input format is key=value | key='value value'.",
                hash,
            )
            continue
        split_hash = hash.split("=", 1)
        result[split_hash[0]] = split_hash[1]
    for key in result:
        if not result.get(key):
            logger.warning(
                "No value assigned to key '%s', input format is key=value | key='value value'.",
                key,
            )
    return result
