"""GitHub CLI-backed implementation of :class:`IssueBackend`.

Every external call is a ``subprocess.run`` with an argv array (no
``shell=True``), an explicit timeout, and structured error handling.
Auth is delegated to ``gh`` itself (``~/.config/gh/hosts.yml``) — we
never read or persist tokens from this code.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Iterable

from hosaka.issues.backend import (
    CommentInput,
    CreateIssueInput,
    DoctorCheck,
    DoctorReport,
    Issue,
    IssueBackend,
    IssueError,
)

DEFAULT_TIMEOUT = 15.0
LIST_JSON_FIELDS = "number,title,state,labels,assignees,updatedAt,url"
SHOW_JSON_FIELDS = "number,title,state,labels,assignees,updatedAt,url,body"


def _run(argv: list[str], timeout: float = DEFAULT_TIMEOUT) -> tuple[int, str, str]:
    """Run ``argv`` without a shell. Returns (rc, stdout, stderr).

    Distinguishes "binary not on PATH" (rc=127) from "ran and failed" so
    callers can render different error text for missing dependencies.
    """
    try:
        proc = subprocess.run(  # noqa: S603 — argv array, shell=False by default
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", f"not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout running {argv[0]}"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _parse_issue_json(raw: dict) -> Issue:
    labels = []
    for lab in raw.get("labels") or []:
        if isinstance(lab, dict):
            name = lab.get("name")
            if name:
                labels.append(name)
        elif isinstance(lab, str):
            labels.append(lab)
    assignees = []
    for ass in raw.get("assignees") or []:
        if isinstance(ass, dict):
            login = ass.get("login")
            if login:
                assignees.append(login)
        elif isinstance(ass, str):
            assignees.append(ass)
    return Issue(
        number=int(raw.get("number") or 0),
        title=str(raw.get("title") or ""),
        state=str(raw.get("state") or "").lower() or "unknown",
        labels=labels,
        url=str(raw.get("url") or ""),
        updated_at=str(raw.get("updatedAt") or ""),
        assignees=assignees,
        body=str(raw.get("body") or ""),
    )


class GhIssueBackend(IssueBackend):
    """Wrap ``gh issue ...`` for Hosaka."""

    name = "gh"

    def __init__(self, repo: str | None = None) -> None:
        self.repo = repo

    # ── helpers ──────────────────────────────────────────────────────────

    def _repo_args(self, override: str | None = None) -> list[str]:
        repo = override or self.repo
        return ["--repo", repo] if repo else []

    def _inferred_repo(self) -> str | None:
        """Best-effort: derive ``owner/name`` from the git remote.

        Returns ``None`` if not inside a git repo or remote is unparseable;
        ``gh`` will then do its own inference at call time.
        """
        rc, out, _ = _run(["git", "remote", "get-url", "origin"], timeout=3.0)
        if rc != 0 or not out:
            return None
        url = out.strip()
        if url.endswith(".git"):
            url = url[:-4]
        if url.startswith("git@github.com:"):
            return url.split(":", 1)[1] or None
        for prefix in ("https://github.com/", "http://github.com/", "ssh://git@github.com/"):
            if url.startswith(prefix):
                return url[len(prefix):] or None
        return None

    # ── doctor ───────────────────────────────────────────────────────────

    def doctor(self) -> DoctorReport:
        checks: list[DoctorCheck] = []

        gh_path = shutil.which("gh")
        if not gh_path:
            checks.append(DoctorCheck("gh installed", False, "install with: sudo apt install gh"))
            return DoctorReport(checks=checks, repo=self.repo)
        checks.append(DoctorCheck("gh installed", True, gh_path))

        rc, out, err = _run(["gh", "auth", "status"], timeout=8.0)
        if rc == 0:
            first_line = next((line.strip() for line in out.splitlines() if line.strip()), "ok")
            checks.append(DoctorCheck("gh authed", True, first_line))
        else:
            detail = err or out or "run: gh auth login"
            checks.append(DoctorCheck("gh authed", False, detail.splitlines()[0] if detail else "run: gh auth login"))

        rc, _, err = _run(["git", "rev-parse", "--is-inside-work-tree"], timeout=3.0)
        inside_repo = rc == 0
        checks.append(DoctorCheck(
            "inside git repo",
            inside_repo,
            "cd into the Hosaka checkout" if not inside_repo else "yes",
        ))

        repo = self.repo or self._inferred_repo()
        if repo:
            checks.append(DoctorCheck("repo detected", True, repo))
        else:
            checks.append(DoctorCheck(
                "repo detected",
                False,
                "no origin remote — pass --repo OWNER/NAME or run inside a clone",
            ))

        return DoctorReport(checks=checks, repo=repo)

    # ── create / list / show ─────────────────────────────────────────────

    def create(self, inp: CreateIssueInput) -> Issue:
        argv = ["gh", "issue", "create", "--title", inp.title, "--body", inp.body or ""]
        argv += self._repo_args(inp.repo)
        labels = list(_dedupe(inp.labels))
        if labels:
            argv += ["--label", ",".join(labels)]

        rc, out, err = _run(argv)
        if rc != 0:
            # Label-missing is non-fatal per the YAML: retry once without labels.
            err_lower = (err or "").lower()
            if labels and (
                "label" in err_lower and ("not found" in err_lower or "could not add" in err_lower)
            ):
                retry = ["gh", "issue", "create", "--title", inp.title, "--body", inp.body or ""]
                retry += self._repo_args(inp.repo)
                rc, out, err = _run(retry)
                if rc != 0:
                    raise IssueError(err or out or "gh issue create failed")
            else:
                raise IssueError(err or out or "gh issue create failed")

        url = out.strip().splitlines()[-1] if out.strip() else ""
        number = _number_from_url(url)
        if not number:
            try:
                return self.list(state="all", repo=inp.repo)[0]
            except Exception as exc:  # pragma: no cover — best effort
                raise IssueError(f"created but could not parse number from: {out!r} ({exc})")
        return Issue(
            number=number,
            title=inp.title,
            state="open",
            labels=labels,
            url=url,
        )

    def list(self, state: str = "open", repo: str | None = None) -> list[Issue]:
        argv = [
            "gh", "issue", "list",
            "--state", state,
            "--limit", "200",
            "--json", LIST_JSON_FIELDS,
        ]
        argv += self._repo_args(repo)
        rc, out, err = _run(argv)
        if rc != 0:
            raise IssueError(err or out or "gh issue list failed")
        try:
            raw = json.loads(out or "[]")
        except json.JSONDecodeError as exc:
            raise IssueError(f"gh returned non-JSON: {exc}") from exc
        return [_parse_issue_json(item) for item in raw]

    def show(self, number: int, repo: str | None = None) -> Issue:
        argv = [
            "gh", "issue", "view", str(number),
            "--json", SHOW_JSON_FIELDS,
        ]
        argv += self._repo_args(repo)
        rc, out, err = _run(argv)
        if rc != 0:
            raise IssueError(err or out or f"gh issue view {number} failed")
        try:
            raw = json.loads(out or "{}")
        except json.JSONDecodeError as exc:
            raise IssueError(f"gh returned non-JSON: {exc}") from exc
        return _parse_issue_json(raw)

    # ── mutate ───────────────────────────────────────────────────────────

    def comment(self, inp: CommentInput) -> None:
        argv = ["gh", "issue", "comment", str(inp.issue_number), "--body", inp.body]
        argv += self._repo_args(inp.repo)
        rc, out, err = _run(argv)
        if rc != 0:
            raise IssueError(err or out or "gh issue comment failed")

    def start(self, number: int, repo: str | None = None) -> None:
        # Best effort: try to add the "in-progress" label. If the label
        # doesn't exist (very common on fresh repos), fall back to a
        # comment so progress is still recorded.
        argv = [
            "gh", "issue", "edit", str(number),
            "--add-label", "in-progress",
        ]
        argv += self._repo_args(repo)
        rc, _, err = _run(argv)
        if rc != 0:
            # Fall back to a comment so the agent contract still records start.
            self.comment(CommentInput(
                issue_number=number,
                body="Agent started work on this issue.",
                repo=repo,
            ))

    def close(self, number: int, body: str, repo: str | None = None) -> None:
        if not body or not body.strip():
            raise IssueError("close requires a non-empty comment (--force not honored at backend layer)")
        argv = [
            "gh", "issue", "close", str(number),
            "--comment", body,
            "--reason", "completed",
        ]
        argv += self._repo_args(repo)
        rc, out, err = _run(argv)
        if rc != 0:
            raise IssueError(err or out or f"gh issue close {number} failed")


def _dedupe(items: Iterable[str]) -> Iterable[str]:
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        yield key


def _number_from_url(url: str) -> int | None:
    if not url:
        return None
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return None
