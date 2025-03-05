# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
common: Defines common utility functions and components.

"""

import base64
import json
import logging
from typing import Dict, List, Optional

from knack.log import get_logger

logger = get_logger(__name__)


def parse_kvp_nargs(kvp_nargs: List[str]) -> dict:
    """
    Parses kvp nargs into a dict handling values of null and empty string.
    """
    result = {}
    if not kvp_nargs:
        return result

    for item in kvp_nargs:
        key, sep, value = item.partition("=")
        result[key] = value if sep else None
    return result


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
    url = "/providers/Microsoft.ResourceGraph/resources?api-version=2022-10-01"
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


def url_safe_hash_phrase(phrase: str) -> str:
    from hashlib import sha256

    return sha256(phrase.encode("utf8")).hexdigest()


def url_safe_random_chars(count: int) -> str:
    import secrets

    token = ""
    while len(token) < count:
        _t = secrets.token_urlsafe()
        _t = _t.replace("-", "")
        _t = _t.replace("_", "")
        token += _t

    return token[:count]


def ensure_azure_namespace_path():
    """
    Run prior to importing azure namespace packages (azure.*) to ensure the
    extension root path is configured for package import.
    """

    import os
    import sys

    from azure.cli.core.extension import get_extension_path

    from ...constants import EXTENSION_NAME

    ext_path = get_extension_path(EXTENSION_NAME)
    if not ext_path:
        return

    ext_azure_dir = os.path.join(ext_path, "azure")
    if os.path.isdir(ext_azure_dir):
        import azure

        if getattr(azure, "__path__", None) and ext_azure_dir not in azure.__path__:  # _NamespacePath /w PEP420
            if isinstance(azure.__path__, list):
                azure.__path__.insert(0, ext_azure_dir)
            else:
                azure.__path__.append(ext_azure_dir)

    if sys.path and sys.path[0] != ext_path:
        sys.path.insert(0, ext_path)


def run_host_command(command: str, shell_mode: bool = True):
    from shlex import quote, split
    from subprocess import run

    if not command:
        raise ValueError("command value is required.")

    logger.debug("Running host command: %s", command)
    command = quote(command)
    split_command = split(command)

    try:
        return run(split_command, capture_output=True, check=False, shell=shell_mode)
    except FileNotFoundError:
        pass


def is_env_flag_enabled(env_flag_key: str) -> bool:
    from os import getenv

    return getenv(env_flag_key, "false").lower() in ["true", "1", "y"]


def is_enabled_str(value: Optional[str]) -> bool:
    """
    Converts an intended property str value (such as from k8s enum) to bool
    """

    if isinstance(value, str):
        return value.lower() == "enabled"

    return False


def should_continue_prompt(confirm_yes: Optional[bool] = None, context: str = "Deletion") -> bool:
    from rich.prompt import Confirm

    if not confirm_yes and not Confirm.ask("Continue?"):
        logger.warning(f"{context} cancelled.")
        return False

    return True


def insert_newlines(s: str, every: int = 79):
    return "\n".join(s[i : i + every] for i in range(0, len(s), every))
