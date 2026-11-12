# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Explicit test-only corrections for one frozen Fairfax release; never patch its wheel."""

import hashlib
import json
from pathlib import Path

from release_monitor_pytest import FAIRFAX_EXCLUSIONS, FAIRFAX_TEST_SOURCE


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "azext_edge/tests/"
BASE_FILES = {
    "edge/orchestration/test_runtime_channels_int.py":
        "002a27f50f6d606346e212bd506f20af91e3897ada72fca4bc8aa1c20f2c2329",
    "edge/orchestration/test_live_data_int.py":
        "5e89d3c4eb721f055dc731b7dd8a4c4596b4aad1a6788b8fde94fc0c6beeb90c",
    "edge/orchestration/resources/registry_endpoint/test_registry_endpoints_int.py":
        "13b4ee051aedcbe09d0e624310b28c7c5f2ebe824d11f8840eb2463c4746cff6",
}


def digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("A reviewed compatibility test file is missing or is a symlink.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compatibility(manifest):
    if (manifest["extension"] != "azure-iot-ops" or manifest["cloud"] != "AzureUSGovernment"
            or manifest["testSourceCommit"] != FAIRFAX_TEST_SOURCE):
        return None
    return {
        "schema": 1, "automationCommit": manifest["automationCommit"],
        "baseTestSourceCommit": FAIRFAX_TEST_SOURCE,
        "files": [
            {"path": PREFIX + name, "baseSha256": base, "sha256": digest(ROOT / PREFIX / name)}
            for name, base in BASE_FILES.items()
        ],
        "exclusions": FAIRFAX_EXCLUSIONS,
    }


def verify_source(source, plan):
    if plan is not None:
        for item in plan["files"]:
            if digest(Path(source) / item["path"]) != item["baseSha256"]:
                raise ValueError("Released tests differ from the reviewed compatibility baseline.")


def stage_tests(target, manifest, output):
    plan = compatibility(manifest)
    if manifest.get("testCompatibility") != plan:
        raise ValueError("Test compatibility differs from the frozen automation manifest.")
    if plan is None:
        return
    verify_source(target, plan)
    replacements = []
    for item in plan["files"]:
        content = (ROOT / item["path"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("Reviewed test compatibility content changed before staging.")
        replacements.append((Path(target) / item["path"], content))
    for path, content in replacements:
        path.write_bytes(content)
    Path(output).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print("Applied test-only compatibility: " + json.dumps(plan, sort_keys=True), flush=True)
