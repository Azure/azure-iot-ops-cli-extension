# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
common: Defines common utility functions and components.

"""

import json
import os
import logging
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

    return _process_raw_request(cmd, url, "POST", payload)


def _process_raw_request(
    cmd, url: str, method: str, payload: Optional[dict] = None, keyword: str = "data"
):
    # since I don't want to download the resourcegraph sdk - we are stuck with this
    # note that we are trying to limit dependencies
    from azure.cli.core.util import send_raw_request

    result = []
    skip_token = "sentinel"
    while skip_token:
        try:
            body = json.dumps(payload) if payload is not None else None
            res = send_raw_request(
                cli_ctx=cmd.cli_ctx, url=url, method=method, body=body
            )
        except Exception as e:
            raise e
        if not res.content:
            return
        json_response = res.json()
        result.extend(json_response[keyword])
        skip_token = json_response.get("$skipToken")
        if skip_token:
            if not payload:
                payload = {"options": {}}
            if "options" not in payload:
                payload["options"] = {}
            payload["options"]["$skipToken"] = skip_token

    return result


def get_timestamp_now_utc(format: str = "%Y-%m-%dT%H:%M:%S") -> str:
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime(format)
    return timestamp


def set_log_level(log_name: str, log_level: int = logging.DEBUG):
    lgr = logging.getLogger(log_name)
    lgr.setLevel(log_level)
