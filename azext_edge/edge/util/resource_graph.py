# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import List, Optional

from azure.cli.core.util import send_raw_request


class ResourceGraph:
    def __init__(self, cmd, subscriptions: Optional[List[str]] = None):
        self.cmd = cmd
        self.subscriptions = subscriptions

    def query(self, query: str) -> List[dict]:
        return self._process_query(query=query)

    def _process_query(self, query: str) -> List[dict]:
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


    def _process_raw_request(self, cmd, url: str, method: str, payload: Optional[dict] = None, keyword: str = "data"):
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
