# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

"""
common: Defines common utility functions and components.

"""

import base64
import json
import logging
from typing import Dict, List, Optional

from azure.cli.core.azclierror import FileOperationError
from knack.log import get_logger

logger = get_logger(__name__)


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


def build_query(cmd, subscription_id: Optional[str] = None, custom_query: Optional[str] = None, **kwargs):
    url = '/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01'
    subscriptions = [subscription_id] if subscription_id else []
    payload = {"subscriptions": subscriptions, "query": "Resources ", "options": {}}

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


def _process_raw_request(cmd, url: str, method: str, payload: Optional[dict] = None, keyword: str = "data"):
    # since I don't want to download the resourcegraph sdk - we are stuck with this
    # note that we are trying to limit dependencies
    from azure.cli.core.util import send_raw_request

    result = []
    skip_token = "sentinel"
    while skip_token:
        try:
            body = json.dumps(payload) if payload is not None else None
            res = send_raw_request(cli_ctx=cmd.cli_ctx, url=url, method=method, body=body)
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


def generate_secret(byte_length=32):
    """
    Generate cryptographically secure secret.
    """
    import secrets

    token_bytes = secrets.token_bytes(byte_length)
    return base64.b64encode(token_bytes).decode("utf8")


def read_file_content(file_path, read_as_binary=False):
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


def url_safe_hash_phrase(phrase: str):
    from hashlib import sha256

    return sha256(phrase.encode("utf8")).hexdigest()
