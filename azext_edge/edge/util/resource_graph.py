# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import List, Optional, TYPE_CHECKING

from azure.cli.core.util import send_raw_request

GRAPH_API_VERSION = "2022-10-01"
GRAPH_RESOURCE_PATH = f"/providers/Microsoft.ResourceGraph/resources?api-version={GRAPH_API_VERSION}"

if TYPE_CHECKING:
    from requests.models import Response


class ResourceGraph:
    def __init__(self, cmd, subscriptions: Optional[List[str]] = None):
        self.cmd = cmd
        self.subscriptions = []
        if subscriptions:
            self.subscriptions.extend(subscriptions)

    def query_resources(self, query: str, page_size: Optional[int] = None) -> dict:
        """Query Azure Resource Graph (ARG).

        Args:
          query: An ARG compatible query string.
          page_size: Integer corresponding to max records per page. Currently Id must be included
            for skipToken paging to work correctly.

        Returns:
          A dict including a 'data' property that has the accumulated resources.
        """
        return self._process_resource_query(query=query, page_size=page_size)

    def _process_resource_query(self, query: str, page_size: Optional[int] = None) -> List[dict]:
        result = {"data": []}
        request_payload = {"subscriptions": self.subscriptions, "query": query, "options": {}}
        if page_size:
            request_payload["options"]["$top"] = page_size

        while True:
            request_body = json.dumps(request_payload)
            # send_raw_request throws azure.cli.core.azclierror.HTTPError on not OK status code.
            raw_request_response: Response = send_raw_request(
                cli_ctx=self.cmd.cli_ctx,
                url=GRAPH_RESOURCE_PATH,
                body=request_body,
                method="POST",
            )
            response_payload: dict = raw_request_response.json()
            result["data"].extend(response_payload.get("data", []))

            if "$skipToken" not in response_payload:
                break

            request_payload["options"] = {"$skipToken": response_payload["$skipToken"]}

        return result
