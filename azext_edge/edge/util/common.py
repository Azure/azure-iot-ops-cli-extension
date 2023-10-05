# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
utility: Defines common utility functions and components.

"""

import json
import os
from typing import List, Dict, Optional
from knack.log import get_logger
from ...common.embedded_cli import EmbeddedCLI


cli = EmbeddedCLI()
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


def build_query(subscription_id: str, custom_query: Optional[str] = None, **kwargs):
    rest_cmd = "rest --method POST --url '/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01' "
    payload = {"subscriptions": [subscription_id], "query": "Resources ", "options": {}}

    # TODO: add more query options as they pop up
    if kwargs.get("location"):
        payload["query"] += f'| where location =~ "{kwargs.get("location")}" '
    if kwargs.get("resource_group"):
        payload["query"] += f'| where resourceGroup =~ "{kwargs.get("resource_group")}" '
    if kwargs.get("type"):
        payload["query"] += f'| where type =~ "{kwargs.get("type")}" '
    if custom_query:
        payload["query"] += custom_query
    payload["query"] += "| project id, location, name, resourceGroup, properties, tags, type, subscriptionId"

    return _process_query(rest_cmd, payload)


def _process_query(rest_cmd: str, payload: dict):
    total_data = []
    skip_token = "sentinel"
    while skip_token:
        try:
            cli.invoke(rest_cmd + f" --body '{json.dumps(payload)}'")
        except Exception as e:
            raise e
        result = cli.as_json()
        page_data = result.get("data")
        if page_data:
            total_data.extend(page_data)
        skip_token = result.get("$skipToken")
        if skip_token:
            payload["options"]["$skipToken"] = skip_token

    return total_data


def get_timestamp_now_utc(format: str = "%Y-%m-%dT%H:%M:%S") -> str:
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime(format)
    return timestamp
