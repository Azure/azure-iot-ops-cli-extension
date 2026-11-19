# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Renew ADO assertions in CLI credential caches without rewriting the account profile."""

import argparse
import json
import logging
import os
from pathlib import Path
import signal
import sys
from threading import Event
from types import SimpleNamespace
from uuid import UUID

import requests


TIMEOUT = (10, 30)


def assertion():
    connection, project, plan, job = (str(UUID(os.environ[name])) for name in (
        "AZURESUBSCRIPTION_SERVICE_CONNECTION_ID", "SYSTEM_TEAMPROJECTID", "SYSTEM_PLANID", "SYSTEM_JOBID",
    ))
    url = (f"https://dev.azure.com/azureiotdevxp/{project}/_apis/distributedtask/hubs/build/"
           f"plans/{plan}/jobs/{job}/oidctoken")
    with requests.post(
        url, params={"serviceConnectionId": connection, "api-version": "7.1-preview.1"},
        headers={"Authorization": "Bearer " + os.environ["SYSTEM_ACCESSTOKEN"]},
        json={}, timeout=TIMEOUT, allow_redirects=False,
    ) as response:
        if response.status_code != 200:
            raise RuntimeError("ADO assertion renewal failed.")
        value = response.json()["oidcToken"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("ADO did not return an assertion.")
    return value


def refresh():
    from azure.cli.core._environment import get_config_dir
    from azure.cli.core._profile import _create_identity_instance
    from azure.cli.core.auth.identity import ServicePrincipalAuth
    from azure.cli.core.auth.msal_credentials import ServicePrincipalCredential
    from azure.cli.core.auth.util import resource_to_scopes
    from azure.cli.core.cloud import get_active_cloud_name, get_cloud
    from knack.config import CLIConfig

    client, tenant, subscription = (
        str(UUID(os.environ[name])) for name in ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "OPS_SUBSCRIPTION")
    )
    config_dir = get_config_dir()
    profile_path = Path(config_dir) / "azureProfile.json"
    before = profile_path.read_bytes()
    profile = json.loads(before.decode("utf-8-sig"))
    cli_ctx = SimpleNamespace(config=CLIConfig(config_dir=config_dir, config_env_var_prefix="AZURE"))
    cli_ctx.cloud = get_cloud(cli_ctx, get_active_cloud_name(cli_ctx))
    accounts = [
        account for account in profile["subscriptions"]
        if account.get("isDefault") and account.get("environmentName") == cli_ctx.cloud.name
    ]
    if len(accounts) != 1:
        raise ValueError("Exactly one current Azure account is required.")
    account = accounts[0]
    user = account.get("user", {})
    if (account["id"].lower() != subscription or account["tenantId"].lower() != tenant
            or user.get("type") != "servicePrincipal" or user.get("name", "").lower() != client):
        raise ValueError("Azure account does not match the authorized ops identity and subscription.")
    # Use CLI's own locked persistence, matching the proven IoT CLI renewal path.
    identity = _create_identity_instance(
        cli_ctx, cli_ctx.cloud.endpoints.active_directory, tenant_id=account["tenantId"],
    )
    auth = ServicePrincipalAuth.build_from_credential(
        identity.tenant_id, user["name"], ServicePrincipalAuth.build_credential(client_assertion=assertion()),
    )
    credential = ServicePrincipalCredential(
        user["name"], auth.get_msal_client_credential(), timeout=TIMEOUT,
        **identity._msal_app_kwargs,  # pylint: disable=protected-access
    )
    credential.acquire_token(resource_to_scopes(cli_ctx.cloud.endpoints.active_directory_resource_id))
    identity._service_principal_store.save_entry(auth.get_entry_to_persist())  # pylint: disable=protected-access
    if profile_path.read_bytes() != before:
        raise RuntimeError("Renewal unexpectedly modified the Azure account profile.")
    print("ADO CLI credential caches refreshed; account profile unchanged.", flush=True)


def failure(exc_type, _exception, _traceback):
    # Auth exceptions can contain assertions or response bodies. Never render their values.
    print(f"##vso[task.logissue type=error]ADO credential renewal failed ({exc_type.__name__}).",
          file=sys.stderr, flush=True)


def main():
    sys.excepthook = failure
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready", type=Path, required=True)
    args = parser.parse_args()
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    refresh()
    args.ready.write_text("ready\n", encoding="ascii")
    while not stopped.wait(240):
        refresh()


if __name__ == "__main__":
    main()
