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


# TODO: unit test
def build_query(cmd, subscription_id: str, custom_query: Optional[str] = None, **kwargs):
    url = '/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01'
    payload = {"subscriptions": [subscription_id], "query": "Resources ", "options": {}}

    # TODO: add more query options as they pop up
    if kwargs.get("name"):
        payload["query"] += f'| where name =~ "{kwargs.get("name")}" '
    if kwargs.get("resource_group"):
        payload["query"] += f'| where resourceGroup =~ "{kwargs.get("resource_group")}" '
    if kwargs.get("location"):
        payload["query"] += f'| where location =~ "{kwargs.get("location")}" '
    if kwargs.get("type"):
        payload["query"] += f'| where type =~ "{kwargs.get("type")}" '
    if custom_query:
        payload["query"] += custom_query
    payload["query"] += "| project id, location, name, resourceGroup, properties, tags, type, subscriptionId"
    if kwargs.get("additional_project"):
        payload["query"] += f', {kwargs.get("additional_project")}'

    return _process_query(cmd, url, "POST", payload)


def _process_query(cmd, url: str, method: str, payload: dict):
    # since we don't want to download the resourcegraph sdk - we are stuck with this
    from azure.cli.core.util import send_raw_request

    r = send_raw_request(
        cli_ctx=cmd.cli_ctx, url=url, method=method, body=json.dumps(payload)
    )

    if r.content:
        return r.json()["data"]


def get_timestamp_now_utc(format: str = "%Y-%m-%dT%H:%M:%S") -> str:
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime(format)
    return timestamp
