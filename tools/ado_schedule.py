# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Fail scheduled health preparation when an older run of this definition is still active."""

import os
from urllib.parse import urlencode

from release_pipeline import ado, environment, identifier


def check_scheduled_overlap():
    if os.environ.get("BUILD_REASON", "").lower() != "schedule":
        return
    definition = identifier(environment("SYSTEM_DEFINITIONID"))
    current = identifier(environment("BUILD_BUILDID"))
    active_statuses = {"inProgress", "notStarted", "postponed", "cancelling"}
    result = ado("build/builds?" + urlencode({
        "definitions": definition, "statusFilter": ",".join(sorted(active_statuses)),
        "queryOrder": "queueTimeAscending", "$top": 1000,
    }))
    if (not isinstance(result, dict) or not isinstance(result.get("value"), list)
            or type(result.get("count")) is not int or result["count"] != len(result["value"])
            or not 0 < result["count"] < 1000):
        raise ValueError("Scheduled overlap preflight could not establish a bounded active-build inventory.")
    seen = set()
    for build in result["value"]:
        if (not isinstance(build, dict) or not isinstance(build.get("definition"), dict)
                or str(build["definition"].get("id")) != definition
                or build.get("status") not in active_statuses):
            raise ValueError("Scheduled overlap preflight received an unexpected active-build identity or status.")
        build_id = identifier(build.get("id"))
        if build_id in seen:
            raise ValueError("Scheduled overlap preflight received duplicate active-build identities.")
        seen.add(build_id)
    if current not in seen:
        raise ValueError("Scheduled overlap preflight could not establish this run in the active-build inventory.")
    older = sorted((value for value in seen if int(value) < int(current)), key=int)
    if older:
        raise RuntimeError(
            f"Scheduled run {current} refused: definition {definition} has older active build(s) "
            f"{', '.join(older)}. Provisioning is blocked; inspect those runs before retrying."
        )
    print(f"Scheduled overlap preflight passed for definition {definition}, build {current}: no older active builds.",
          flush=True)
