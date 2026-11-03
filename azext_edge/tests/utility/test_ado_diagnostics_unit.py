# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Failure evidence survives hook deletion without copying credentials or pod specifications."""

import json
import subprocess
from unittest.mock import Mock
from zipfile import ZipFile

from azext_edge.tests.utility.test_ado_integration_unit import cluster


diagnostics = cluster.diagnostics


def test_sanitization_removes_credentials_and_pipeline_commands(monkeypatch):
    monkeypatch.setenv("SYSTEM_ACCESSTOKEN", "offline-sensitive-token")
    text = (
        "known offline-sensitive-token\nAuthorization: Bearer abc\npassword=private\n"
        "url=https://user:pass@example.test/path?sig=signed\n"
        "eyJheader.eyJbody.signature\n-----BEGIN PRIVATE KEY-----\nprivate\n-----END PRIVATE KEY-----\n"
        "##vso[task.complete result=Succeeded;]fake\nBackoffLimitExceeded exitCode=1"
    )
    result = diagnostics.sanitize(text)
    for secret in ("offline-sensitive-token", "Bearer abc", "private", "signed", "user:pass", "eyJheader", "##vso["):
        assert secret not in result
    assert "BackoffLimitExceeded exitCode=1" in result


def test_hook_snapshot_retains_logs_before_deletion_and_publishes_early(tmp_path, monkeypatch, capsys):
    collector = diagnostics.HookCollector(tmp_path, tmp_path / "owned", "ops-k3s-owned", "ops-diagnostics-owned-1")
    job = {
        "kind": "Job",
        "metadata": {"uid": "job-uid", "name": "broker-hook", "annotations": {"helm.sh/hook": "pre-upgrade"}},
        "spec": {"template": {"spec": {"containers": [{"env": [{"value": "do-not-export"}]}]}}},
        "status": {"failed": 1},
    }
    pod = {
        "kind": "Pod", "metadata": {"uid": "pod-uid", "name": "hook-pod", "ownerReferences": [{"uid": "job-uid"}]},
        "spec": {"containers": [{"name": "hook", "image": "example/hook:1", "env": [{"value": "do-not-export"}]}]},
        "status": {"phase": "Failed", "containerStatuses": [{"name": "hook", "restartCount": 1}]},
    }
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        if "jobs,pods" in arguments:
            return json.dumps({"items": [job, pod]})
        if "events" in arguments:
            return '{"reason": "BackoffLimitExceeded"}'
        return "hook failed: exit 1\npassword=do-not-export"

    monkeypatch.setattr(diagnostics, "command", run)
    collector.snapshot()
    assert collector.uploads == 1
    assert any("--previous=true" in arguments for arguments in calls)
    assert all(arguments[1:3] == ["--kubeconfig", str(tmp_path / "owned/user-config")] for arguments in calls)
    with ZipFile(tmp_path / "diagnostics/hooks-1.zip") as archive:
        contents = "\n".join(archive.read(name).decode() for name in archive.namelist())
    assert "do-not-export" not in contents and "hook failed: exit 1" in contents
    assert "artifact.upload" in capsys.readouterr().out
    monkeypatch.setattr(diagnostics, "command", Mock(return_value='{"items": []}'))
    collector.snapshot()
    assert (collector.folder / "pod-uid-hook-current.log").is_file()
    assert collector.uploads == 1


def test_api_failure_still_retains_owned_k3s_journal_and_reports_error(tmp_path, monkeypatch, capsys):
    collector = diagnostics.HookCollector(tmp_path, tmp_path, "ops-k3s-owned", "ops-diagnostics-owned-1")
    monkeypatch.setattr(diagnostics, "command", Mock(side_effect=subprocess.TimeoutExpired("kubectl", 10)))
    journal = Mock(return_value="k3s exited with status 1")
    monkeypatch.setattr(diagnostics, "journal", journal)
    collector.finish(failed=True)
    journal.assert_called_once_with("ops-k3s-owned")
    assert (collector.folder / "k3s-journal.log").read_text() == "k3s exited with status 1"
    output = capsys.readouterr().out
    assert "type=warning" in output and "artifact.upload" in output
