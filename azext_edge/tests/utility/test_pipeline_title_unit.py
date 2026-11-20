# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.

from pathlib import Path
import runpy
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[3]
TITLE = runpy.run_path(str(ROOT / "tools/pipeline_title.py"))


@pytest.mark.parametrize("prefix,version,fields,expected", [
    ("iot", "1.0.1", {"scopes": ["ADU"], "regions": ["australiaeast"]},
     "iot-123 (1.0.1) (ADU) (australiaeast)"),
    ("ops", "2.11.2",
     {"scopes": ["edge"], "regions": ["westus2"], "runtimes": ["1.5.45"], "channels": ["stable"]},
     "ops-123 (2.11.2) (edge) (westus2) (runtime 1.5.45) (stable)"),
    ("ops", "2.11.2", {"action": "validate"}, "ops-123 (2.11.2) (validate)"),
    ("ops", None, {"scopes": ["edge"], "regions": ["westus2"]}, "ops-123"),
    ("clean", None, {}, "clean-123"),
])
def test_title_orders_frozen_metadata_and_omits_inapplicable_groups(prefix, version, fields, expected):
    assert TITLE["format_title"](prefix, "123", version, **fields) == expected


def test_title_compacts_only_whole_scope_and_region_items():
    title = TITLE["format_title"](
        "ops", "123", "2.11.2", scopes=["edge", "upgrade", "livedata", "redeploy"],
        regions=["westus2", "eastus2", "centralus", "australiaeast"],
    )
    assert title == "ops-123 (2.11.2) (edge, upgrade, livedata +1) (australiaeast, centralus, eastus2 +1)"


@pytest.mark.parametrize("fields", [
    {"version": "2.11.2]\n##vso[build.updatebuildnumber]other"},
    {"version": "2.11.2", "scopes": ["edge) (other"]},
    {"version": "2.11.2", "regions": ["West US 2"]},
    {"version": "2.11.2", "channels": ["canary"]},
    {"version": "2.11.2", "action": "upload"},
])
def test_title_rejects_unsafe_or_unapproved_fields(fields):
    with pytest.raises(ValueError):
        TITLE["format_title"]("ops", "123", **fields)


@pytest.mark.parametrize("prefix", ["ops", "clean"])
def test_id_only_titles_still_enforce_the_ado_length_limit(prefix):
    with pytest.raises(ValueError, match="name limit"):
        TITLE["format_title"](prefix, "9" * 256)


def test_title_reads_exact_wheel_metadata_not_filename_or_host_version(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILD_BUILDNUMBER", "old-name (99.0.0)")
    wheel = tmp_path / "candidate.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("azext_edge/__init__.py", "")
        archive.writestr("azure_iot_ops-2.11.2.dist-info/METADATA", "Name: azure-iot-ops\nVersion: 2.11.2\n")
    assert TITLE["wheel_version"](tmp_path) == "2.11.2"
    (tmp_path / "second.whl").write_bytes(wheel.read_bytes())
    with pytest.raises(ValueError, match="Exactly one"):
        TITLE["wheel_version"](tmp_path)


def test_title_reads_bundled_runtime_without_executing_code_or_applying_health_policy(tmp_path):
    wheel = tmp_path / "candidate.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr(
            "azext_edge/edge/providers/orchestration/template.py",
            "raise AssertionError('must not execute product code')\n"
            "P = {'VERSIONS': {'iotOperations': '1.99.0-dev.1'}, 'TRAINS': {'iotOperations': 'integration'}}\n",
        )
    assert TITLE["wheel_runtimes"](wheel, ["stable"]) == ["1.99.0-dev.1"]
    with pytest.raises(ValueError, match="missing"):
        TITLE["wheel_runtimes"](wheel, ["preview"])
