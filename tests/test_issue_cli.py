"""Unit tests for `hosaka issue` CLI + gh backend.

All `subprocess.run` calls are intercepted via monkeypatch; no actual
`gh` invocations happen. We assert on:

* argv shape (no shell=True, correct flags, --repo flow-through)
* JSON output mode
* close-without-comment safety
* label-missing fallback retry
* doctor's missing-gh path
"""
from __future__ import annotations

import io
import json
import subprocess
from contextlib import redirect_stdout
from dataclasses import dataclass

import pytest

from hosaka.issues import cli as issue_cli
from hosaka.issues import gh_backend
from hosaka.issues.backend import IssueError


@dataclass
class FakeProc:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class _Recorder:
    """Drop-in replacement for subprocess.run that records argv and returns scripted outputs."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.script: list[FakeProc] = []
        self.default = FakeProc(0, "", "")

    def queue(self, *procs: FakeProc) -> None:
        self.script.extend(procs)

    def __call__(self, argv, *args, **kwargs):
        assert kwargs.get("shell", False) is False, "shell=True is forbidden"
        assert isinstance(argv, list), "argv must be a list, not a string"
        self.calls.append(argv)
        if self.script:
            return self.script.pop(0)
        return self.default


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(gh_backend.subprocess, "run", rec)
    return rec


# ── doctor ───────────────────────────────────────────────────────────────


def test_doctor_missing_gh(monkeypatch, recorder):
    monkeypatch.setattr(gh_backend.shutil, "which", lambda name: None)
    rc = issue_cli.main(["--repo", "x/y", "doctor"])
    assert rc == 1


def test_doctor_happy_path(monkeypatch, recorder):
    monkeypatch.setattr(gh_backend.shutil, "which", lambda name: "/usr/bin/gh")
    recorder.queue(
        FakeProc(0, "github.com\n  Logged in to github.com", ""),  # gh auth status
        FakeProc(0, "true", ""),                                   # git rev-parse
    )
    rc = issue_cli.main(["--repo", "x/y", "doctor"])
    assert rc == 0
    # gh auth status + git rev-parse
    assert recorder.calls[0][:3] == ["gh", "auth", "status"]
    assert recorder.calls[1][:2] == ["git", "rev-parse"]


def test_doctor_json_mode(monkeypatch, recorder, capsys):
    monkeypatch.setattr(gh_backend.shutil, "which", lambda name: "/usr/bin/gh")
    recorder.queue(
        FakeProc(0, "github.com", ""),
        FakeProc(0, "true", ""),
    )
    rc = issue_cli.main(["--repo", "x/y", "--json", "doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["repo"] == "x/y"
    assert all("name" in c for c in payload["checks"])


# ── new ──────────────────────────────────────────────────────────────────


def test_new_builds_correct_argv(recorder):
    recorder.queue(FakeProc(0, "https://github.com/x/y/issues/42", ""))
    rc = issue_cli.main([
        "--repo", "x/y", "new", "Test title",
        "--body", "details", "--label", "ux",
    ])
    assert rc == 0
    argv = recorder.calls[0]
    assert argv[:3] == ["gh", "issue", "create"]
    assert "--title" in argv and "Test title" in argv
    assert "--body" in argv
    assert "--repo" in argv and "x/y" in argv
    # default labels hosaka,agent must appear plus the explicit ux
    assert "--label" in argv
    label_arg = argv[argv.index("--label") + 1]
    assert "hosaka" in label_arg and "agent" in label_arg and "ux" in label_arg


def test_new_label_missing_retries_without_labels(recorder):
    recorder.queue(
        FakeProc(1, "", "could not add label: 'hosaka' not found"),
        FakeProc(0, "https://github.com/x/y/issues/7", ""),
    )
    rc = issue_cli.main(["--repo", "x/y", "new", "T"])
    assert rc == 0
    assert len(recorder.calls) == 2
    # Second call should not contain --label
    assert "--label" not in recorder.calls[1]


def test_new_template_wraps_body(recorder):
    recorder.queue(FakeProc(0, "https://github.com/x/y/issues/1", ""))
    rc = issue_cli.main([
        "--repo", "x/y", "new", "Bug title",
        "--body", "boom", "--template", "bug",
    ])
    assert rc == 0
    argv = recorder.calls[0]
    body = argv[argv.index("--body") + 1]
    assert "## Bug" in body
    assert "boom" in body
    assert "## Reproduction" in body


# ── list / show ──────────────────────────────────────────────────────────


def test_list_parses_json(recorder, capsys):
    payload = [
        {
            "number": 1, "title": "first", "state": "OPEN",
            "labels": [{"name": "hosaka"}], "assignees": [],
            "updatedAt": "2026-05-01T00:00:00Z",
            "url": "https://github.com/x/y/issues/1",
        }
    ]
    recorder.queue(FakeProc(0, json.dumps(payload), ""))
    rc = issue_cli.main(["--repo", "x/y", "list"])
    assert rc == 0
    argv = recorder.calls[0]
    assert argv[:3] == ["gh", "issue", "list"]
    assert "--json" in argv
    assert "--repo" in argv and "x/y" in argv
    out = capsys.readouterr().out
    assert "#   1" in out
    assert "first" in out


def test_list_json_mode(recorder, capsys):
    recorder.queue(FakeProc(0, "[]", ""))
    rc = issue_cli.main(["--repo", "x/y", "--json", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out) == []


# ── note / done ──────────────────────────────────────────────────────────


def test_note_argv_shape(recorder):
    recorder.queue(FakeProc(0, "", ""))
    rc = issue_cli.main(["--repo", "x/y", "note", "5", "progress comment"])
    assert rc == 0
    argv = recorder.calls[0]
    assert argv[:4] == ["gh", "issue", "comment", "5"]
    assert argv[argv.index("--body") + 1] == "progress comment"


def test_done_requires_comment(recorder, capsys):
    rc = issue_cli.main(["--repo", "x/y", "done", "5"])
    assert rc == 2
    assert recorder.calls == []  # never reached the backend
    err = capsys.readouterr().err
    assert "requires a closing comment" in err


def test_done_force_allows_empty(recorder):
    recorder.queue(FakeProc(0, "", ""))
    rc = issue_cli.main(["--repo", "x/y", "done", "5", "--force"])
    assert rc == 0
    argv = recorder.calls[0]
    assert argv[:4] == ["gh", "issue", "close", "5"]
    assert "--reason" in argv and "completed" in argv
    assert "--comment" in argv


def test_done_with_comment(recorder):
    recorder.queue(FakeProc(0, "", ""))
    rc = issue_cli.main(["--repo", "x/y", "done", "5", "verified on pi 5"])
    assert rc == 0
    argv = recorder.calls[0]
    assert argv[argv.index("--comment") + 1] == "verified on pi 5"


# ── safety invariants ───────────────────────────────────────────────────


def test_no_shell_true_anywhere(recorder):
    # Run a representative set; recorder asserts shell=False on every call.
    recorder.queue(FakeProc(0, "[]", ""))
    issue_cli.main(["--repo", "x/y", "list"])
    recorder.queue(FakeProc(0, "https://github.com/x/y/issues/1", ""))
    issue_cli.main(["--repo", "x/y", "new", "T"])
    recorder.queue(FakeProc(0, "", ""))
    issue_cli.main(["--repo", "x/y", "note", "1", "hi"])
    # No assert needed — recorder.__call__ asserts shell=False.


def test_backend_error_returns_exit_2(recorder, capsys):
    recorder.queue(FakeProc(1, "", "boom"))
    rc = issue_cli.main(["--repo", "x/y", "note", "1", "hi"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "boom" in err
