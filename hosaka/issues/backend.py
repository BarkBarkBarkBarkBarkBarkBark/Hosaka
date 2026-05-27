"""Backend interface + dataclasses for the Hosaka issue tracker.

Concrete backends (``GhIssueBackend``, future ``GitBugIssueBackend``,
``TaskwarriorBackend``, ``TeaIssueBackend``) implement :class:`IssueBackend`.
The CLI in :mod:`hosaka.issues.cli` only talks to the ABC, so swapping
backends is a one-line change in the dispatcher.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class IssueError(RuntimeError):
    """Raised by backends for any user-actionable failure.

    The CLI catches this and prints ``stderr``-friendly text; it does
    not bubble traceback noise to the operator.
    """


@dataclass
class Issue:
    """A tracked issue as the CLI sees it.

    Backends should normalize their native representation into this
    shape so the CLI can render human + JSON output uniformly.
    """

    number: int
    title: str
    state: str
    labels: list[str] = field(default_factory=list)
    url: str = ""
    updated_at: str = ""
    assignees: list[str] = field(default_factory=list)
    body: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "state": self.state,
            "labels": list(self.labels),
            "url": self.url,
            "updated_at": self.updated_at,
            "assignees": list(self.assignees),
            "body": self.body,
        }


@dataclass
class CreateIssueInput:
    title: str
    body: str = ""
    labels: list[str] = field(default_factory=list)
    repo: str | None = None


@dataclass
class CommentInput:
    issue_number: int
    body: str
    repo: str | None = None


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass
class DoctorReport:
    checks: list[DoctorCheck] = field(default_factory=list)
    repo: str | None = None

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "repo": self.repo,
            "checks": [c.to_json() for c in self.checks],
        }


class IssueBackend(ABC):
    """Pluggable backend for the Hosaka issue CLI.

    Implementations MUST NOT use ``shell=True`` in any subprocess call,
    MUST NOT store auth tokens in repo files, and MUST raise
    :class:`IssueError` (not bare exceptions) for user-actionable
    failures so the CLI can render them cleanly.
    """

    name: str = "abstract"

    @abstractmethod
    def doctor(self) -> DoctorReport:
        """Return a structured health report for the backend.

        Must never raise on missing dependencies; instead, report them
        as failed checks so the CLI can print actionable hints.
        """

    @abstractmethod
    def create(self, inp: CreateIssueInput) -> Issue:
        """Create a new issue. Returns the created issue."""

    @abstractmethod
    def list(self, state: str = "open", repo: str | None = None) -> list[Issue]:
        """List issues, optionally filtered by state (open/closed/all)."""

    @abstractmethod
    def show(self, number: int, repo: str | None = None) -> Issue:
        """Fetch a single issue by number."""

    @abstractmethod
    def comment(self, inp: CommentInput) -> None:
        """Append a comment to an existing issue."""

    @abstractmethod
    def start(self, number: int, repo: str | None = None) -> None:
        """Mark an issue as in-progress (label or comment, best effort)."""

    @abstractmethod
    def close(self, number: int, body: str, repo: str | None = None) -> None:
        """Close an issue with a final comment.

        Per the agent safety contract, callers must supply ``body``;
        the CLI enforces this unless an explicit ``--force`` is given.
        """
