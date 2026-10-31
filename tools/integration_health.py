# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Resolve ADO Library profiles using the immutable run's branch and queued UTC day."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ado_integration import producer, read, required


DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
CLUSTER_REGIONS = {
    "eastus", "eastus2", "westus", "westus2", "westus3", "southcentralus",
    "westeurope", "northeurope", "germanywestcentral",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_metadata():
    request = Request(
        f"https://dev.azure.com/azureiotdevxp/aziotcli/_apis/build/builds/{producer()['build']}?api-version=7.1",
        headers={"Authorization": "Bearer " + required("SYSTEM_ACCESSTOKEN")},
    )
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"ADO health lookup failed with HTTP {error.code}.") from None


def choose(configuration, build):
    branch = required("BUILD_SOURCEBRANCH")
    current = producer()
    if (str(build["id"]) != current["build"] or str(build["definition"]["id"]) != current["pipeline"]
            or build["sourceVersion"] != current["commit"] or build["sourceBranch"] != branch):
        raise ValueError("ADO source identity differs from this run.")
    queued = datetime.fromisoformat(build["queueTime"].replace("Z", "+00:00"))
    if queued.tzinfo is None:
        raise ValueError("Queue time must include a timezone.")
    day = DAYS[queued.astimezone(timezone.utc).weekday()]
    if not isinstance(configuration, dict) or set(configuration) != {"schema", "branches"}:
        raise ValueError("ValidationProfiles requires schema and branches.")
    if (type(configuration["schema"]) is not int or configuration["schema"] != 1
            or not isinstance(configuration["branches"], dict)):
        raise ValueError("Unsupported ValidationProfiles schema.")
    choices = configuration["branches"].get(branch)
    if not isinstance(choices, dict) or not set(choices) <= set(DAYS) or day not in choices:
        raise ValueError(f"No valid profile for {branch} on {day}.")
    return {
        "schema": 1, "producer": current, "branch": branch, "queuedAt": queued.isoformat(),
        "day": day, "profile": choices[day],
        "configurationSha256": hashlib.sha256(
            json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def validate(profile):
    keys = {"clusterRegion", "resourceRegion", "namespaceRegion", "pythonVersions",
            "scenarios", "runtimeChannels", "scenarioTimeoutMinutes", "upgradeBaselines"}
    if not isinstance(profile, dict) or set(profile) != keys:
        raise ValueError("Ops health profile has missing or unexpected fields.")
    if not isinstance(profile["clusterRegion"], str) or profile["clusterRegion"] not in CLUSTER_REGIONS:
        raise ValueError("Select a supported Arc/AIO cluster region.")
    for name in ("resourceRegion", "namespaceRegion"):
        if not isinstance(profile[name], str) or not re.fullmatch(r"[a-z0-9]{1,40}", profile[name]):
            raise ValueError(f"Invalid {name}.")
    for name in ("pythonVersions", "scenarios", "runtimeChannels"):
        values = profile[name]
        if (not isinstance(values, list) or not values or not all(isinstance(item, str) and item for item in values)
                or len(values) != len(set(values))):
            raise ValueError(f"Select distinct {name}.")
    if type(profile["scenarioTimeoutMinutes"]) is not int or profile["scenarioTimeoutMinutes"] not in (90, 180, 360):
        raise ValueError("Scenario timeout must be 90, 180 or 360 minutes.")
    if not isinstance(profile["upgradeBaselines"], dict):
        raise ValueError("Upgrade baselines must be an object.")


def resolve(history):
    previous = sorted(Path(history).glob("ops-plan-*/plan.json"))
    if previous:
        plans = [read(path) for path in previous]
        if (any(plan != plans[0] for plan in plans) or plans[0]["producer"] != producer()
                or plans[0].get("health", {}).get("branch") != required("BUILD_SOURCEBRANCH")):
            raise ValueError("Health plan history changed or belongs to another run.")
        value = plans[0]["health"]
    else:
        try:
            configuration = json.loads(os.environ.get("VALIDATION_PROFILES", ""))
        except json.JSONDecodeError:
            raise ValueError("ValidationProfiles must contain valid JSON.") from None
        value = choose(configuration, build_metadata())
    validate(value["profile"])
    profile = value["profile"]
    for name, key in (("OPS_SCENARIOS", "scenarios"), ("OPS_CHANNELS", "runtimeChannels"),
                      ("OPS_PYTHONS", "pythonVersions")):
        os.environ[name] = ",".join(profile[key])
    os.environ["OPS_BASELINES"] = json.dumps(profile["upgradeBaselines"])
    os.environ["OPS_SCENARIO_TIMEOUT_MINUTES"] = str(profile["scenarioTimeoutMinutes"])
    return value
