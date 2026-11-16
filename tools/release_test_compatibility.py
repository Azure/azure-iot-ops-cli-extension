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

from release_monitor_pytest import (
    FAIRFAX_EXCLUSIONS,
    FAIRFAX_TEST_SOURCE,
    PUBLIC_V2_TEST_SOURCE,
    PUBLIC_V3_TEST_SOURCE,
    exclusions_for,
)


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "azext_edge/tests/"
BASE_FILES = {
    "edge/orchestration/test_runtime_channels_int.py":
        "002a27f50f6d606346e212bd506f20af91e3897ada72fca4bc8aa1c20f2c2329",
    "edge/orchestration/test_live_data_int.py":
        "5e89d3c4eb721f055dc731b7dd8a4c4596b4aad1a6788b8fde94fc0c6beeb90c",
    "edge/orchestration/resources/registry_endpoint/test_registry_endpoints_int.py":
        "13b4ee051aedcbe09d0e624310b28c7c5f2ebe824d11f8840eb2463c4746cff6",
    "edge/orchestration/resources/test_schema_int.py":
        "013709a13ffbd074a49a088d95259b9a7ccabf7e1100360a93e34afc65149ce8",
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
ADR_DEVICE_META_FLAGS = " --manufacturer Contoso --model DeviceModel --os Linux --os-version 1.0"
SOURCE_PATCHES = {
    ("AzureCloud", PUBLIC_V2_TEST_SOURCE): [
        {
            "path": "edge/adr/conftest.py",
            "kind": "adr_shared_device_metadata",
            "baseSha256": "a6ccd4ed9990de0b705bbdda007d48a410a63c47a55a7f942314ed21efdb8c91",
        },
        {
            "path": "edge/adr/test_namespace_devices_int.py",
            "kind": "adr_generalized_endpoint_device_metadata",
            "baseSha256": "b613ade9854e4d0c2622b582abdc80abc6be5f30ef286bf4cdf4e43aca81c60d",
        },
        {
            "path": "edge/orchestration/test_mgmt_actions_int.py",
            "kind": "adr_mgmt_actions_device_metadata",
            "baseSha256": "3ff4c7c43dda85ebb15fed48d5837369258e6adaf9b2a10ada7050f17cc5945e",
        },
    ],
    ("AzureCloud", PUBLIC_V3_TEST_SOURCE): [
        {
            "path": "edge/adr/conftest.py",
            "kind": "adr_shared_device_metadata",
            "baseSha256": "ce4adc90c3af2daf081a5f6efbbd7e3719b3e47c506f319fbfb146edd31f3aaa",
        },
        {
            "path": "edge/adr/test_namespace_devices_int.py",
            "kind": "adr_generalized_endpoint_device_metadata",
            "baseSha256": "b613ade9854e4d0c2622b582abdc80abc6be5f30ef286bf4cdf4e43aca81c60d",
        },
        {
            "path": "edge/support/create_bundle_int/helpers.py",
            "kind": "optional_arc_metrics_agent_helper",
            "baseSha256": "b78a9c6ff0d171d0a795dd0667bd5240616435d627700b2ba1f13272daa9e6b5",
        },
        {
            "path": "edge/support/create_bundle_int/test_arcagents_int.py",
            "kind": "optional_arc_metrics_agent_test",
            "baseSha256": "82af101c349e12c3c5fe8a738236db8128234474fa6c3800aaf55bc81ad73fb0",
        },
        {
            "path": "edge/support/create_bundle_int/test_auto_int.py",
            "kind": "optional_arc_metrics_agent_auto_test",
            "baseSha256": "c8a06a0cd20bae6833c63d255ca375d4e911e71abc07f6659bec8b7335170bd9",
        },
    ],
}


def digest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("A reviewed compatibility test file is missing or is a symlink.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compatibility(manifest):
    cloud = manifest["cloud"]
    source = manifest["testSourceCommit"]
    if manifest["extension"] != "azure-iot-ops" or cloud not in ("AzureCloud", "AzureUSGovernment"):
        return None
    if source == FAIRFAX_TEST_SOURCE:
        fairfax = cloud == "AzureUSGovernment"
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
    patches = SOURCE_PATCHES.get((cloud, source))
    exclusions = exclusions_for(cloud, source)
    if not patches and not exclusions:
        return None
    return {
        "schema": 1,
        "automationCommit": manifest["automationCommit"],
        "baseTestSourceCommit": source,
        "files": [],
        "exclusions": exclusions,
        "secretSyncRemoval": None,
        "sourcePatches": [
            {"path": PREFIX + item["path"], "kind": item["kind"], "baseSha256": item["baseSha256"]}
            for item in (patches or ())
        ],
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
        patches = plan.get("sourcePatches") or []
        for item in plan["files"] + removal["files"] + patches:
            if digest(Path(source) / item["path"]) != item["baseSha256"]:
                raise ValueError("Released tests differ from the reviewed compatibility baseline.")


def _replace_once_in_function(source, function_name, target, replacement):
    tree = ast.parse(source)
    node, = [
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    ]
    lines = source.splitlines(keepends=True)
    segment = "".join(lines[node.lineno - 1:node.end_lineno])
    if segment.count(target) != 1:
        raise ValueError(f"Expected single compatibility target in {function_name}.")
    lines[node.lineno - 1:node.end_lineno] = [segment.replace(target, replacement, 1)]
    return "".join(lines)


def apply_source_patch(source, kind):
    shared_create = (
        '    result = run(\n'
        '        f"az iot ops ns device create --name {device_name} "\n'
        '        f"--instance {instance_name} -g {resource_group}"\n'
        '    )'
    )
    shared_create_with_meta = (
        '    result = run(\n'
        '        f"az iot ops ns device create --name {device_name} "\n'
        '        f"--instance {instance_name} -g {resource_group}"\n'
        f'        "{ADR_DEVICE_META_FLAGS}"\n'
        '    )'
    )
    if kind == "adr_shared_device_metadata":
        result = _replace_once_in_function(source, "shared_device", shared_create, shared_create_with_meta)
    elif kind == "adr_generalized_endpoint_device_metadata":
        result = _replace_once_in_function(
            source,
            "test_generalized_inbound_endpoint_lifecycle",
            shared_create,
            shared_create_with_meta,
        )
    elif kind == "adr_mgmt_actions_device_metadata":
        target = 'run(f"az iot ops ns device create -n {device_name} {common}")'
        replacement = f'run(f"az iot ops ns device create -n {{device_name}} {{common}}{ADR_DEVICE_META_FLAGS}")'
        result = _replace_once_in_function(source, "mgmt_actions_setup", target, replacement)
    elif kind == "optional_arc_metrics_agent_helper":
        cleanup_target = (
            '    if arc_namespace:\n'
            '        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, arc_namespace, "arcagents"))\n'
            '        assert level_2["folders"] == [agent[0] for agent in ARC_AGENTS], '
            'f"Mismatch; folders: [{level_2[\'folders\']}]"\n'
            '        assert not level_2["files"]'
        )
        cleanup_replacement = (
            '    if arc_namespace:\n'
            '        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, arc_namespace, "arcagents"))\n'
            '        expected_arc_folders = [\n'
            '            agent[0] for agent in ARC_AGENTS\n'
            '            if agent[0] != "metrics-agent" or "metrics-agent" in level_2["folders"]\n'
            '        ]\n'
            '        assert level_2["folders"] == expected_arc_folders, '
            'f"Mismatch; folders: [{level_2[\'folders\']}]"\n'
            '        assert not level_2["files"]'
        )
        target = (
            '        for agent, _ in ARC_AGENTS:\n'
            '            agent_path = path.join(BASE_ZIP_PATH, arc_namespace, "arcagents", agent)\n'
            '            file_map["arc"][agent] = convert_file_names(walk_result[agent_path]["files"])'
        )
        replacement = (
            '        for agent, _ in ARC_AGENTS:\n'
            '            agent_path = path.join(BASE_ZIP_PATH, arc_namespace, "arcagents", agent)\n'
            '            if agent == "metrics-agent" and agent_path not in walk_result:\n'
            '                num_additional_services -= 1\n'
            '                continue\n'
            '            file_map["arc"][agent] = convert_file_names(walk_result[agent_path]["files"])'
        )
        result = _replace_once_in_function(source, "_clean_up_folders", cleanup_target, cleanup_replacement)
        result = _replace_once_in_function(result, "get_file_map", target, replacement)
    elif kind == "optional_arc_metrics_agent_test":
        target = (
            '    for agent, has_service in ARC_AGENTS:\n'
            '        file_map = agents_file_map[agent]'
        )
        replacement = (
            '    for agent, has_service in ARC_AGENTS:\n'
            '        if agent == "metrics-agent" and agent not in agents_file_map:\n'
            '            continue\n'
            '        file_map = agents_file_map[agent]'
        )
        result = _replace_once_in_function(source, "test_create_bundle_arcagents", target, replacement)
    elif kind == "optional_arc_metrics_agent_auto_test":
        target = "    actual_walk_result = len(expected_services) + int(is_billing_included) + len(ARC_AGENTS)"
        replacement = (
            "    missing_metrics = int(\n"
            "        bool(arc_namespace)\n"
            '        and path.join(BASE_ZIP_PATH, arc_namespace, "arcagents", "metrics-agent") not in walk_result\n'
            "    )\n"
            "    actual_walk_result = (\n"
            "        len(expected_services) + int(is_billing_included) + len(ARC_AGENTS) - missing_metrics\n"
            "    )"
        )
        result = _replace_once_in_function(source, "test_create_bundle", target, replacement)
    else:
        raise ValueError(f"Unsupported compatibility patch kind: {kind}")
    ast.parse(result)
    return result.encode("utf-8")


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
    for item in plan.get("sourcePatches") or []:
        path = Path(target) / item["path"]
        replacements.append((path, apply_source_patch(path.read_text(encoding="utf-8"), item["kind"])))
    for path, content in replacements:
        path.write_bytes(content)
    Path(output).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print("Applied test-only compatibility: " + json.dumps(plan, sort_keys=True), flush=True)
