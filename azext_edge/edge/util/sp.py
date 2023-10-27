# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
from base64 import b64decode
from typing import Tuple

from azure.cli.core._profile import Profile
from azure.cli.core.azclierror import HTTPError


def get_token_claims(cli_ctx) -> dict:
    result = {}
    try:
        profile = Profile(cli_ctx=cli_ctx)
        cred, _, _ = profile.get_login_credentials(resource="https://graph.microsoft.com/")
        claims = json.loads(b64decode(cred.get_token().token.split(".")[1] + "=="))
        result.update(claims)
    except Exception:
        pass
    return result


def principal_is_app(cli_ctx) -> Tuple[bool, str]:
    claims: dict = get_token_claims(cli_ctx)
    id_type = claims.get("idtyp")
    if id_type == "app":
        return True, claims.get("appid")
    return False, None


def sp_can_fetch_self(cli_ctx, app_id: str):
    from azure.cli.core.util import send_raw_request

    try:
        send_raw_request(
            cli_ctx=cli_ctx,
            method="GET",
            url=f"https://graph.microsoft.com/v1.0/applications/{app_id}",
        ).json()
        return True
    except HTTPError as http_error:
        if http_error.response.status_code in [401, 403]:
            return False
        raise http_error
