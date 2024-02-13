# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import os
import re

import requests
from datetime import datetime, timedelta
from azure.cli.core._session import Session
from knack.log import get_logger
from rich.console import Console

from ...constants import VERSION as CURRENT_CLI_VERSION

logger = get_logger(__name__)

GH_BASE_RAW_CONTENT_ENDPOINT = "https://raw.githubusercontent.com/"
GH_CLI_CONSTANTS_ENDPOINT = (
    f"{GH_BASE_RAW_CONTENT_ENDPOINT}digimaun/azure-iot-ops-cli-extension/dev/azext_edge/constants.py"
)
SESSION_FILE_NAME = "iotOpsVersion.json"
SESSION_KEY_LAST_FETCHED = "lastFetched"
SESSION_KEY_LATEST_VERSION = "latestVersion"

console = Console(width=88, stderr=True, highlight=False, safe_box=True)


# TODO: --only-show-errors
def check_latest(cmd):
    # with console.status("Checking for updates..."):
    #     sleep(0.5)
    index = IndexManager(cmd)
    upgrade_semver = index.upgrade_available()
    if upgrade_semver:
        console.print(
            "[dim italic]Update is available. Install with 'az extension --upgrade --name azure-iot-ops'.",
        )


class IndexManager:
    def __init__(self, cmd, min_notify_hours: int = 2):
        self.cmd = cmd
        self.config_dir = self.cmd.cli_ctx.config.config_dir
        self.iot_ops_session = Session()
        self.iot_ops_session.load(os.path.join(self.config_dir, SESSION_FILE_NAME))

    def upgrade_available(self) -> bool:
        from packaging import version

        try:
            latest_cli_version = CURRENT_CLI_VERSION
            last_fetched = self.iot_ops_session.get(SESSION_KEY_LAST_FETCHED)
            if last_fetched:
                last_fetched = datetime.strptime(last_fetched, "%Y-%m-%d %H:%M:%S.%f")
            if not last_fetched or datetime.now() < last_fetched + timedelta(days=1):
                # Record attempted last fetch
                self.iot_ops_session[SESSION_KEY_LAST_FETCHED] = str(datetime.now())
                if check_connectivity(url=GH_CLI_CONSTANTS_ENDPOINT):
                    latest_cli_version = get_latest_from_github(url=GH_CLI_CONSTANTS_ENDPOINT)
                    self.iot_ops_session[SESSION_KEY_LATEST_VERSION] = latest_cli_version

            return version.parse(latest_cli_version) > version.parse(CURRENT_CLI_VERSION)
        except Exception as ae:
            logger.debug(ae)

        return False


def get_latest_from_github(url: str = GH_CLI_CONSTANTS_ENDPOINT) -> str:
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            logger.debug(
                "Failed to fetch the latest version from '%s' with status code '%s' and reason '%s'",
                url,
                response.status_code,
                response.reason,
            )
            return None
        for line in response.iter_lines():
            txt = line.decode("utf-8", errors="ignore")
            if txt.startswith("VERSION"):
                match = re.search(r"VERSION = \"(.*)\"$", txt)
                if match:
                    return match.group(1)
    except Exception as ex:  # pylint: disable=broad-except
        logger.info("Failed to get the latest version from '%s'. %s", url, str(ex))
        return None


def check_connectivity(url, max_retries=3, timeout=10):
    import timeit

    start = timeit.default_timer()
    success = None
    try:
        with requests.Session() as s:
            s.mount(url, requests.adapters.HTTPAdapter(max_retries=max_retries))
            s.head(url, timeout=timeout)
            success = True
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as ex:
        logger.info("Connectivity problem detected.")
        logger.debug(ex)
        success = False
    stop = timeit.default_timer()
    logger.debug("Connectivity check: %s sec", stop - start)
    return success
