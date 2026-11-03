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
            return '{"items": [{"reason": "BackoffLimitExceeded"}]}'
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


def test_crashing_runtime_pod_logs_are_retained_without_a_hook(tmp_path, monkeypatch):
    collector = diagnostics.HookCollector(tmp_path, tmp_path, "ops-k3s-owned", "ops-diagnostics-owned-1")
    pod = {
        "kind": "Pod", "metadata": {"uid": "broker-uid", "name": "aio-broker-backend-1-0"},
        "spec": {"containers": [{"name": "broker", "image": "example/broker:1",
                                "env": [{"name": "PASSWORD", "value": "do-not-export"}]}]},
        "status": {"phase": "Running", "containerStatuses": [
            {"name": "broker", "ready": False, "restartCount": 2,
             "state": {"waiting": {"reason": "CrashLoopBackOff"}}},
        ]},
    }
    healthy = {
        "kind": "Pod", "metadata": {"uid": "healthy-uid", "name": "healthy"},
        "status": {"phase": "Running", "containerStatuses": [{"name": "healthy", "ready": True}]},
    }
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        if "jobs,pods" in arguments:
            return json.dumps({"items": [healthy, pod]})
        return "broker exited before readiness\npassword=do-not-export"

    monkeypatch.setattr(diagnostics, "command", run)
    collector.snapshot()
    assert (collector.folder / "broker-uid-broker-current.log").is_file()
    assert (collector.folder / "broker-uid-broker-previous.log").is_file()
    assert not any("logs" in arguments and "healthy" in arguments for arguments in calls)
    saved = (collector.folder / "broker-uid.json").read_text()
    assert json.loads(saved)["status"]["containerStatuses"][0]["restartCount"] == 2
    assert "do-not-export" not in saved
    monkeypatch.setattr(diagnostics, "command", Mock(return_value='{"items": []}'))
    collector.snapshot()
    assert "broker exited before readiness" in (collector.folder / "broker-uid-broker-previous.log").read_text()


def test_large_events_remain_valid_json_and_prioritize_warnings(tmp_path, monkeypatch):
    collector = diagnostics.HookCollector(tmp_path, tmp_path, "ops-k3s-owned", "ops-diagnostics-owned-1")
    events = [
        {"type": "Normal", "message": "started " + "x" * 1000, "lastTimestamp": "2026-11-03T05:10:00Z",
         "involvedObject": {"kind": "Pod", "name": f"healthy-{index}"}} for index in range(100)
    ] + [
        {"type": "Warning", "reason": "BackOff", "message": "broker keeps crashing",
         "lastTimestamp": "2026-11-03T05:00:00Z", "involvedObject": {"name": "broker"}},
        {"type": "Warning", "message": "authorization: private-value",
         "lastTimestamp": "2026-11-03T05:01:00Z"},
    ]
    monkeypatch.setattr(diagnostics, "command", Mock(return_value=json.dumps({"items": events})))
    collector.events()
    text = (collector.folder / "events.json").read_text()
    saved = json.loads(text)
    assert len(text.encode()) <= diagnostics.LIMIT
    assert saved["omitted"] == len(events) - len(saved["items"]) > 0
    assert saved["items"][0]["lastTimestamp"] == "2026-11-03T05:01:00Z"
    assert saved["items"][1]["reason"] == "BackOff"
    assert saved["items"][1]["object"]["name"] == "broker"
    assert "private-value" not in text
    collector.save_json("status.json", {"message": "authorization: private-value", "phase": "Failed"})
    assert json.loads((collector.folder / "status.json").read_text())["phase"] == "Failed"


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
