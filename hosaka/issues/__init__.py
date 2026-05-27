"""Hosaka issue tracking — terminal-first wrapper over a pluggable backend.

Default backend is :class:`hosaka.issues.gh_backend.GhIssueBackend`, which
shells out to the GitHub CLI (``gh issue ...``). Future backends
(``git-bug``, Taskwarrior, Forgejo/Gitea Tea) implement the same
:class:`IssueBackend` ABC so the CLI surface and agent contract stay stable
across hosts.

The agent contract is "No issue, no work" — any non-trivial bug, feature,
hardware integration, or install problem becomes a tracked issue before
work begins. See ``docs/issue-tracking.md`` for the human guide.
"""

from hosaka.issues.backend import (
    CommentInput,
    CreateIssueInput,
    DoctorCheck,
    DoctorReport,
    Issue,
    IssueBackend,
    IssueError,
)
from hosaka.issues.gh_backend import GhIssueBackend

__all__ = [
    "CommentInput",
    "CreateIssueInput",
    "DoctorCheck",
    "DoctorReport",
    "Issue",
    "IssueBackend",
    "IssueError",
    "GhIssueBackend",
]
