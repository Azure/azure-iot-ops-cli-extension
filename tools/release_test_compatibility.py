# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Explicit test-only corrections for frozen releases; never patch their wheels."""

import ast
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
OPCUA_PREFIX = "edge/orchestration/resources/connector/opcua/int/"
REMOVAL_FUNCTION = "assert_ssc_secret_not_exists"
REMOVAL_FILES = {
    OPCUA_PREFIX + "helpers.py": "0c6bfdb52c5841e153374bc68048988c5df89ae54cce49205211720e63f6781b",
    OPCUA_PREFIX + "test_opcua_certs_trust_int.py":
        "55c9ad2913ca416bf70bffcbbc749baa49b72f0cb657a026d56c5c6db321a387",
    OPCUA_PREFIX + "test_opcua_certs_issuer_int.py":
        "57670666d81589f5acfb7d28c1c660f674506eb880a353262ac4fb6f06f3ac67",
    OPCUA_PREFIX + "test_opcua_certs_client_int.py":
        "fcc5433e80defe6a54daae2c8ddded00840755771bfe328261472cd0bf1a9391",
}


def digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("A reviewed compatibility test file is missing or is a symlink.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compatibility(manifest):
    if (manifest["extension"] != "azure-iot-ops" or manifest["cloud"] not in ("AzureCloud", "AzureUSGovernment")
            or manifest["testSourceCommit"] != FAIRFAX_TEST_SOURCE):
        return None
    fairfax = manifest["cloud"] == "AzureUSGovernment"
    return {
        "schema": 1, "automationCommit": manifest["automationCommit"],
        "baseTestSourceCommit": FAIRFAX_TEST_SOURCE,
        "files": [
            {"path": PREFIX + name, "baseSha256": base, "sha256": digest(ROOT / PREFIX / name)}
            for name, base in (BASE_FILES.items() if fairfax else ())
        ],
        "exclusions": FAIRFAX_EXCLUSIONS if fairfax else {},
        "secretSyncRemoval": {
            "functionSha256": hashlib.sha256(removal_function().encode()).hexdigest(),
            "files": [{"path": PREFIX + name, "baseSha256": base} for name, base in REMOVAL_FILES.items()],
        } if REMOVAL_FILES else None,
    }


def removal_function():
    path = ROOT / PREFIX / OPCUA_PREFIX / "helpers.py"
    digest(path)
    source = path.read_text(encoding="utf-8")
    node, = [item for item in ast.parse(source).body
             if isinstance(item, ast.FunctionDef) and item.name == REMOVAL_FUNCTION]
    return ast.get_source_segment(source, node)


def verify_source(source, plan):
    if plan is not None:
        removal = plan.get("secretSyncRemoval") or {"files": []}
        for item in plan["files"] + removal["files"]:
            if digest(Path(source) / item["path"]) != item["baseSha256"]:
                raise ValueError("Released tests differ from the reviewed compatibility baseline.")


def patch_removal(source, helper, replacement):
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    if helper:
        node, = [item for item in tree.body
                 if isinstance(item, ast.FunctionDef) and item.name == REMOVAL_FUNCTION]
        lines[node.lineno - 1:node.end_lineno] = [replacement + "\n"]
    else:
        node, = [item for item in ast.walk(tree) if isinstance(item, ast.Call)
                 and isinstance(item.func, ast.Name) and item.func.id == REMOVAL_FUNCTION]
        lines.insert(node.lineno, " " * (node.col_offset + 4) + "instance_name=instance_name,\n")
    result = "".join(lines)
    ast.parse(result)
    return result.encode()


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
    removal = plan.get("secretSyncRemoval")
    replacement = removal_function() if removal else None
    if removal and hashlib.sha256(replacement.encode()).hexdigest() != removal["functionSha256"]:
        raise ValueError("Reviewed test compatibility content changed before staging.")
    for item in (removal or {"files": []})["files"]:
        path = Path(target) / item["path"]
        replacements.append((
            path, patch_removal(path.read_text(encoding="utf-8"), path.name == "helpers.py", replacement),
        ))
    for path, content in replacements:
        path.write_bytes(content)
    Path(output).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print("Applied test-only compatibility: " + json.dumps(plan, sort_keys=True), flush=True)
