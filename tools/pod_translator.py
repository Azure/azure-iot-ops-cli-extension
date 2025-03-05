# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
import os
import json
import sys
from unittest import TestCase
from zipfile import ZipFile
from rich.console import Console
from datetime import datetime, timezone

import yaml

from azext_edge.edge.util.common import get_timestamp_now_utc


def process_supportbundle(bundle_path: str, output_format: str = "json"):
    if output_format not in ["json", "txt"]:
        raise ValueError(f"Unsupported output format: {output_format}")

    data = []
    with ZipFile(bundle_path, "r") as zip:
        # find all pod .yaml file names
        file_names = zip.namelist()
        pod_file_names = [
            name for name in file_names if name.endswith(".yaml") and "metric" not in name and "pod" in name
        ]

        for file_name in pod_file_names:
            with zip.open(file_name) as pod_content:
                log_content = pod_content.read().decode("utf-8")
                data.append(translate_pod(content=log_content))

    # sort data by namespace and name
    data.sort(key=lambda x: (x["namespace"], x["name"]))

    output_ext = "json" if output_format == "json" else "txt"
    output_template_path = f"./translated_pods.{output_ext}"

    with open(output_template_path, "w") as write_file:
        if output_format == "json":
            write_file.write(json.dumps(data, indent=2))
        elif output_format == "txt":
            table = convert_to_table(data)
            console = Console(file=write_file)
            console.print(table)

    # Test serialized content
    with open(output_template_path, "r") as read_file:
        content = read_file.read()

    if output_format == "json":
        payload_to_integrate = json.loads(content)
        assert payload_to_integrate == data
        TestCase().assertEqual(data, payload_to_integrate)
    elif output_format == "txt":
        payload_to_integrate = content
        test_file_path = "./test_file.txt"
        with open(test_file_path, "w") as write_file:
            console = Console(file=write_file)
            console.print(table)

        with open(test_file_path, "r") as read_file:
            expected_content = read_file.read()
            assert payload_to_integrate == expected_content
            TestCase().assertEqual(expected_content, payload_to_integrate)

        # remove the test file
        os.remove(test_file_path)

    print("Expected data assertions passed!")


def translate_pod(content: str):
    # Load the YAML content
    log = yaml.safe_load(content)

    translated = {"name": log["metadata"]["name"], "namespace": log["metadata"]["namespace"]}
    container_statuses = log["status"].get("containerStatuses", [])

    pod_deletion_timestamp = log["metadata"].get("deletionTimestamp", None)
    pod_phase = log["status"]["phase"]

    # Determine pod status
    if pod_deletion_timestamp and pod_phase not in ["failed", "succeeded"]:
        translated["status"] = "Terminating"
    else:
        translated["status"] = pod_phase.capitalize()

    readiness = sum(1 for status in container_statuses if status.get("ready"))
    restart_count = sum(status.get("restartCount", 0) for status in container_statuses)

    translated["restarts"] = restart_count
    translated["containersReady"] = f"{readiness}/{len(container_statuses)}"

    # Ensure the datetime object is in UTC
    created_at = datetime.fromisoformat(log["metadata"]["creationTimestamp"]).replace(tzinfo=timezone.utc)

    # get current time
    current_time = datetime.fromisoformat(get_timestamp_now_utc()).replace(tzinfo=timezone.utc)
    translated["age"] = str(current_time - created_at)

    # Overwrite pod status using reason to be more descriptive if in special state
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


def convert_to_table(data: list):
    from rich.table import Table

    table = Table(title="Pod Health Summary")

    table.add_column("Name", justify="left", no_wrap=True)
    table.add_column("Namespace", justify="left")
    table.add_column("Status", justify="right")
    table.add_column("Restarts", justify="right")
    table.add_column("Containers Ready", justify="right")
    table.add_column("Age", justify="right")

    for pod in data:
        table.add_row(
            pod["name"],
            pod["namespace"],
            pod["status"],
            str(pod["restarts"]),
            pod["containersReady"],
            pod["age"],
        )

    return table


if __name__ == "__main__":
    len_argv = len(sys.argv)
    if len_argv < 2 or len_argv > 3:
        print("Usage: python pod_translator.py <input path to support_bundle.zip> [output file format (json,txt)]")
        raise sys.exit(1)
    process_supportbundle(*sys.argv[1:])
    sys.exit(0)
