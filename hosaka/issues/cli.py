"""``hosaka issue`` argparse CLI.

This is the public surface called by ``python -m hosaka.issues`` and by
the ``hosaka issue`` bash wrapper in ``scripts/hosaka``. The CLI is
backend-agnostic: it talks to an :class:`IssueBackend` via the ABC.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from hosaka.issues.backend import (
    CommentInput,
    CreateIssueInput,
    Issue,
    IssueBackend,
    IssueError,
)
from hosaka.issues.gh_backend import GhIssueBackend

DEFAULT_LABELS = ["hosaka", "agent"]

TEMPLATES: dict[str, str] = {
    "default": (
        "## Context\n"
        "Created from Hosaka terminal issue workflow.\n\n"
        "## Problem / Goal\n"
        "{body}\n\n"
        "## Expected outcome\n"
        "\n\n"
        "## Evidence / Logs\n"
        "\n\n"
        "## Agent notes\n"
        "- Status: opened\n"
        "- Next action: triage\n"
    ),
    "bug": (
        "## Bug\n"
        "{body}\n\n"
        "## Environment\n"
        "- Device:\n"
        "- OS:\n"
        "- Branch:\n"
        "- Commit:\n\n"
        "## Reproduction\n"
        "1.\n"
        "2.\n"
        "3.\n\n"
        "## Expected behavior\n\n\n"
        "## Actual behavior\n\n\n"
        "## Logs / screenshots\n\n\n"
        "## Verification plan\n"
    ),
    "feature": (
        "## Feature\n"
        "{body}\n\n"
        "## Why it matters\n\n\n"
        "## Proposed behavior\n\n\n"
        "## Acceptance criteria\n"
        "- [ ] CLI command exists\n"
        "- [ ] Works from repo root\n"
        "- [ ] Agent can call it safely\n"
        "- [ ] Human-readable output exists\n"
        "- [ ] JSON output exists where useful\n"
        "- [ ] Docs updated\n"
    ),
}


# ── output helpers ───────────────────────────────────────────────────────


def _emit(obj, *, as_json: bool, human_fn) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True, default=_json_default))
    else:
        human_fn()


def _json_default(o):
    if hasattr(o, "to_json"):
        return o.to_json()
    raise TypeError(f"not JSON-serializable: {type(o)!r}")


def _render_issue_row(issue: Issue) -> str:
    labels = ",".join(issue.labels) if issue.labels else "-"
    return f"#{issue.number:>4} [{issue.state:<6}] {issue.title}   ({labels})"


def _render_issue_full(issue: Issue) -> str:
    parts = [
        f"#{issue.number}  {issue.title}",
        f"  state    : {issue.state}",
        f"  labels   : {', '.join(issue.labels) if issue.labels else '-'}",
        f"  url      : {issue.url}",
        f"  updated  : {issue.updated_at}",
        f"  assignees: {', '.join(issue.assignees) if issue.assignees else '-'}",
    ]
    if issue.body:
        parts.append("")
        parts.append(issue.body.rstrip())
    return "\n".join(parts)


def _apply_template(template: str, body: str) -> str:
    tmpl = TEMPLATES.get(template, TEMPLATES["default"])
    return tmpl.replace("{body}", (body or "").strip())


# ── dispatch ─────────────────────────────────────────────────────────────


def _make_backend(args: argparse.Namespace) -> IssueBackend:
    # Single-backend MVP; future: --backend gh|gitbug|task|tea.
    return GhIssueBackend(repo=args.repo)


def cmd_doctor(args: argparse.Namespace, backend: IssueBackend) -> int:
    report = backend.doctor()

    def human() -> None:
        print("hosaka issue doctor")
        for c in report.checks:
            mark = "ok " if c.ok else "FAIL"
            print(f"  [{mark}] {c.name:<18} {c.detail}")
        print(f"  repo: {report.repo or '(unknown)'}")
        if not report.ok:
            print("\nhint: fix the failing checks above and re-run.", file=sys.stderr)

    _emit(report, as_json=args.json, human_fn=human)
    return 0 if report.ok else 1


def cmd_new(args: argparse.Namespace, backend: IssueBackend) -> int:
    body = _apply_template(args.template, args.body or "")
    labels = list(DEFAULT_LABELS)
    for lab in args.label or []:
        labels.append(lab)
    inp = CreateIssueInput(title=args.title, body=body, labels=labels, repo=args.repo)
    try:
        issue = backend.create(inp)
    except IssueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    def human() -> None:
        print(f"created #{issue.number}: {issue.title}")
        if issue.url:
            print(f"  {issue.url}")

    _emit(issue, as_json=args.json, human_fn=human)
    return 0


def cmd_list(args: argparse.Namespace, backend: IssueBackend) -> int:
    try:
        issues = backend.list(state=args.state, repo=args.repo)
    except IssueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    def human() -> None:
        if not issues:
            print(f"(no {args.state} issues)")
            return
        for issue in issues:
            print(_render_issue_row(issue))

    _emit([i.to_json() for i in issues], as_json=args.json, human_fn=human)
    return 0


def cmd_show(args: argparse.Namespace, backend: IssueBackend) -> int:
    try:
        issue = backend.show(args.number, repo=args.repo)
    except IssueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _emit(issue, as_json=args.json, human_fn=lambda: print(_render_issue_full(issue)))
    return 0


def cmd_note(args: argparse.Namespace, backend: IssueBackend) -> int:
    try:
        backend.comment(CommentInput(issue_number=args.number, body=args.body, repo=args.repo))
    except IssueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    def human() -> None:
        print(f"commented on #{args.number}")

    _emit({"ok": True, "number": args.number}, as_json=args.json, human_fn=human)
    return 0


def cmd_start(args: argparse.Namespace, backend: IssueBackend) -> int:
    try:
        backend.start(args.number, repo=args.repo)
    except IssueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    def human() -> None:
        print(f"marked #{args.number} in-progress")

    _emit({"ok": True, "number": args.number}, as_json=args.json, human_fn=human)
    return 0


def cmd_done(args: argparse.Namespace, backend: IssueBackend) -> int:
    body = args.body
    if not body or not body.strip():
        if not args.force:
            print(
                "error: `done` requires a closing comment. Pass it as the second arg, "
                "or use --force to close without one.",
                file=sys.stderr,
            )
            return 2
        body = "Closed via `hosaka issue done --force` (no closing comment supplied)."
    try:
        backend.close(args.number, body=body, repo=args.repo)
    except IssueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    def human() -> None:
        print(f"closed #{args.number}")

    _emit({"ok": True, "number": args.number}, as_json=args.json, human_fn=human)
    return 0


# ── argparse wiring ──────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hosaka issue",
        description=(
            "Persistent issue tracking for Hosaka. Wraps `gh issue ...` so "
            "humans and agents share one durable backlog. "
            "Contract: no issue, no work."
        ),
    )
    p.add_argument("--repo", help="Override repo as OWNER/NAME (default: infer from git remote)")
    p.add_argument("--json", action="store_true", help="Emit structured JSON instead of human text")

    sub = p.add_subparsers(dest="command", required=True)

    s_doctor = sub.add_parser("doctor", help="Check gh install, auth, and repo detection")
    s_doctor.set_defaults(func=cmd_doctor)

    s_new = sub.add_parser("new", help="Create a new issue")
    s_new.add_argument("title", help="Issue title")
    s_new.add_argument("--body", "-b", default="", help="Free-form body. Wrapped in the selected template.")
    s_new.add_argument(
        "--template", "-t",
        choices=sorted(TEMPLATES.keys()),
        default="default",
        help="Body template (default|bug|feature)",
    )
    s_new.add_argument(
        "--label", "-l",
        action="append",
        default=[],
        help="Extra label (repeatable). `hosaka` and `agent` are added automatically.",
    )
    s_new.set_defaults(func=cmd_new)

    s_list = sub.add_parser("list", help="List issues")
    s_list.add_argument("--state", "-s", default="open", choices=["open", "closed", "all"])
    s_list.set_defaults(func=cmd_list)

    s_show = sub.add_parser("show", help="Show one issue")
    s_show.add_argument("number", type=int)
    s_show.set_defaults(func=cmd_show)

    s_note = sub.add_parser("note", help="Comment on an issue")
    s_note.add_argument("number", type=int)
    s_note.add_argument("body")
    s_note.set_defaults(func=cmd_note)

    s_start = sub.add_parser("start", help="Mark an issue in-progress (label or comment)")
    s_start.add_argument("number", type=int)
    s_start.set_defaults(func=cmd_start)

    s_done = sub.add_parser("done", help="Close an issue with a final comment")
    s_done.add_argument("number", type=int)
    s_done.add_argument("body", nargs="?", default="", help="Closing comment (required unless --force)")
    s_done.add_argument("--force", action="store_true", help="Allow closing without a comment")
    s_done.set_defaults(func=cmd_done)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    backend = _make_backend(args)
    try:
        return args.func(args, backend)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
