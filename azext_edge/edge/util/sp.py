# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
from base64 import b64decode
from typing import NamedTuple, Optional

from azure.cli.core._profile import Profile
from azure.cli.core.azclierror import HTTPError
from azure.cli.core.util import send_raw_request


class AppPrincipal(NamedTuple):
    app_id: str
    object_id: str
    app: dict


class LoggedInPrincipal:
    def __init__(self, cmd):
        self.cli_ctx = cmd.cli_ctx
        self.claims = self._get_token_claims()

    def _get_token_claims(self):
        result = {}
        try:
            profile = Profile(cli_ctx=self.cli_ctx)
            cred, _, _ = profile.get_login_credentials(resource="https://graph.microsoft.com/")
            claims = json.loads(b64decode(cred.get_token().token.split(".")[1] + "=="))
            result.update(claims)
        except Exception:
            pass
        return result

    def is_app(self) -> bool:
        id_type = self.claims.get("idtyp")
        return id_type == "app"

    def fetch_self_if_app(self) -> Optional[AppPrincipal]:
        if self.is_app():
            app_id = self.claims.get("appid")
            obj_id = self.claims.get("oid")
            if app_id:
                try:
                    result = send_raw_request(
                        cli_ctx=self.cli_ctx,
                        method="GET",
                        url=f"https://graph.microsoft.com/v1.0/applications/{app_id}",
                    ).json()
                    return AppPrincipal(app_id=app_id, object_id=obj_id, app=result)
                except HTTPError as http_error:
                    if http_error.response.status_code in [401, 403]:
                        return None
                    raise http_error
