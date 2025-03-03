# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
from datetime import datetime, timezone
import json
import sys
from ast import literal_eval
from subprocess import run
from unittest import TestCase
from zipfile import ZipFile

import yaml

from azext_edge.edge.util.common import get_timestamp_now_utc


def process_supportbundle(bundle_path: str):
    data = []
    with ZipFile(bundle_path, "r") as zip:
        # find all pod .yaml file names
        file_names = zip.namelist()
        pod_file_names = [
            name for name in file_names if name.endswith(".yaml") and not "metric" in name and "pod" in name
        ]

        for file_name in pod_file_names:
            with zip.open(file_name) as pod_content:
                log_content = pod_content.read().decode("utf-8")
                data.append(translated_pod(content=log_content))

    with open("translated_pods.txt", "w") as pod_names:
        pod_names.write("\n".join(pod_file_names))

    with open("translated_pods.json", "w") as write_file:
        write_file.write(json.dumps(data, indent=2))


def translated_pod(content: str):
    translated = {}

    # Load the YAML content
    log = yaml.safe_load(content)
    translated["name"] = log["metadata"]["name"]
    translated["namespace"] = log["metadata"]["namespace"]
    container_statuses = log["status"]["containerStatuses"]

    pod_deletion_timestamp = log["metadata"].get("deletionTimestamp", None)
    pod_phase = log["status"]["phase"]

    if pod_deletion_timestamp and pod_phase.lower() != "failed" and pod_phase.lower() != "succeeded":
        translated["status"] = "Terminating"
    else:
        translated["status"] = pod_phase

    readiness = 0
    restart_count = 0

    # Ensure the datetime object is in UTC
    created_at = datetime.fromisoformat(log["metadata"]["creationTimestamp"]).astimezone(timezone.utc)
    for status in container_statuses:
        if status["ready"]:
            readiness += 1
        if "restartCount" in status:
            restart_count += status["restartCount"]

    # get current time
    current_time = datetime.fromisoformat(get_timestamp_now_utc()).astimezone(timezone.utc)
    translated["age"] = str(current_time - created_at)
    translated["restarts"] = restart_count
    translated["ready"] = f"{readiness}/{len(container_statuses)}"
    is_pod_terminated = pod_phase.lower() == "failed" or pod_phase.lower() == "succeeded"
    if is_pod_terminated:
        # status is the reason for termination
        translated["status"] = [
            status["state"]["terminated"]["reason"] for status in container_statuses if "terminated" in status["state"]
        ][0]

    if not is_pod_terminated and pod_phase.lower() == "running" and readiness != len(container_statuses):
        # status is the reason for waiting
        wait_reasons = [
            status["state"]["waiting"]["reason"] for status in container_statuses if "waiting" in status["state"]
        ]
        if wait_reasons:
            translated["status"] = wait_reasons[0]

    return translated


if __name__ == "__main__":
    len_argv = len(sys.argv)
    if len_argv < 1 or len_argv > 2:
        print("Usage: python pod_translator.py <input path to support_bundle.zip>")
        raise sys.exit(1)
    process_supportbundle(*sys.argv[1:])
    sys.exit(0)
