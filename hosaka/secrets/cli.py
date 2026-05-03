"""``python -m hosaka.secrets`` — backing logic for ``hosaka secrets`` verbs."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
from typing import Iterable

from hosaka.secrets import check, spec, store


def _redact(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]} ({len(value)} chars)"


def _print_mirror(result: store.MirrorResult) -> None:
    if result.ok:
        print(f"✓ mirrored to {result.path}")
        return
    print(f"! could not mirror to {result.path}: {result.detail}", file=sys.stderr)
    print(
        f"  run as root to retry: sudo -E {sys.executable} -m hosaka.secrets mirror",
        file=sys.stderr,
    )


def _format_check(result: check.CheckResult) -> str:
    badges = {
        check.STATUS_OK: "✓",
        check.STATUS_MISSING: "✗" if result.required else "·",
        check.STATUS_INVALID: "✗",
        check.STATUS_UNREACHABLE: "?",
        check.STATUS_SKIPPED: "·",
    }
    badge = badges.get(result.status, "·")
    label = "required" if result.required else "optional"
    head = f"{badge} {result.name:<32} [{result.status}] ({label})"
    extras: list[str] = []
    if result.source:
        extras.append(f"source={result.source}")
    if result.detail:
        extras.append(result.detail)
    if extras:
        return head + "\n    " + " — ".join(extras)
    return head


# ── verbs ──────────────────────────────────────────────────────────────────


def cmd_list(args: argparse.Namespace) -> int:
    values = store.load()
    keys: Iterable[str] = sorted(set(values) | {k.name for k in spec.all_keys()})
    for name in keys:
        key_spec = spec.find(name)
        present = name in values
        env_value = os.environ.get(name, "")
        source = ""
        display = ""
        if present:
            source = "~/.hosaka/secrets.json"
            display = _redact(values[name]) if (key_spec is None or key_spec.secret) else values[name]
        elif env_value:
            source = "env"
            display = _redact(env_value) if (key_spec is None or key_spec.secret) else env_value
        elif key_spec is not None and key_spec.default is not None:
            source = "default"
            display = key_spec.default
        else:
            display = "(unset)"
        purpose = key_spec.purpose if key_spec else ""
        line = f"  {name:<32}  {display}"
        if source:
            line += f"  [{source}]"
        if purpose:
            line += f"  — {purpose}"
        print(line)
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    value = store.get(args.name)
    if value is None:
        value = os.environ.get(args.name, "")
    if not value:
        print(f"(unset) {args.name}", file=sys.stderr)
        return 1
    if args.reveal:
        print(value)
    else:
        print(_redact(value))
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    value = args.value
    if value is None:
        if sys.stdin.isatty():
            value = getpass.getpass(f"value for {args.name} (input hidden): ")
        else:
            value = sys.stdin.read().strip()
    if not value:
        print(f"refusing to set {args.name} to empty", file=sys.stderr)
        return 2
    result = store.set(args.name, value, mirror=not args.no_mirror)
    print(f"✓ set {args.name} ({_redact(value)})")
    if not args.no_mirror:
        _print_mirror(result)
    return 0


def cmd_unset(args: argparse.Namespace) -> int:
    if args.name not in store.load():
        print(f"  {args.name} was not in ~/.hosaka/secrets.json")
        return 0
    result = store.unset(args.name, mirror=not args.no_mirror)
    print(f"✓ removed {args.name}")
    if not args.no_mirror:
        _print_mirror(result)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    results = check.run_checks(
        required_only=args.required_only,
        probe=not args.no_probe,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        for r in results:
            print(_format_check(r))
    return 1 if check.has_failures(results) else 0


def cmd_mirror(args: argparse.Namespace) -> int:
    values = store.load()
    result = store.write_env_mirror(values)
    _print_mirror(result)
    return 0 if result.ok else 1


def cmd_import_picoclaw(args: argparse.Namespace) -> int:
    key, source = store.import_from_picoclaw_security()
    if not key:
        print("no key found in ~/.picoclaw/.security.yml", file=sys.stderr)
        return 1
    result = store.set("OPENAI_API_KEY", key, mirror=not args.no_mirror)
    print(f"✓ imported OPENAI_API_KEY from {source} ({_redact(key)})")
    if not args.no_mirror:
        _print_mirror(result)
    return 0


def cmd_edit(args: argparse.Namespace) -> int:
    target = store.env_path()
    sudoedit = shutil.which("sudoedit") or shutil.which("sudo")
    editor = os.environ.get("EDITOR", "nano")
    if sudoedit and "sudoedit" in sudoedit:
        cmd = [sudoedit, str(target)]
    elif sudoedit:
        cmd = [sudoedit, "-e", "--", editor, str(target)]
    else:
        cmd = [editor, str(target)]
    print(f"› {' '.join(cmd)}")
    return subprocess.call(cmd)


def cmd_path(args: argparse.Namespace) -> int:
    print(f"json: {store.json_path()}")
    print(f"env:  {store.env_path()}")
    return 0


# ── entrypoint ────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hosaka.secrets", description=__doc__)
    sub = parser.add_subparsers(dest="verb", required=True)

    p = sub.add_parser("list", help="show every known key (redacted)")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("get", help="print one secret (redacted by default)")
    p.add_argument("name")
    p.add_argument("--reveal", action="store_true", help="print the raw value")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("set", help="store a secret; mirrors to /etc/hosaka/env")
    p.add_argument("name")
    p.add_argument("value", nargs="?", help="if omitted, prompts (hidden) or reads stdin")
    p.add_argument("--no-mirror", action="store_true", help="skip /etc/hosaka/env update")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("unset", help="remove a secret")
    p.add_argument("name")
    p.add_argument("--no-mirror", action="store_true")
    p.set_defaults(func=cmd_unset)

    p = sub.add_parser("check", help="presence + format + live OpenAI probe")
    p.add_argument("--required-only", action="store_true")
    p.add_argument("--no-probe", action="store_true", help="skip live API calls")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--timeout", type=float, default=5.0)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("mirror", help="rewrite /etc/hosaka/env from the JSON store")
    p.set_defaults(func=cmd_mirror)

    p = sub.add_parser(
        "import-picoclaw",
        help="copy OPENAI_API_KEY from ~/.picoclaw/.security.yml into the JSON store",
    )
    p.add_argument("--no-mirror", action="store_true")
    p.set_defaults(func=cmd_import_picoclaw)

    p = sub.add_parser("edit", help="open /etc/hosaka/env in $EDITOR via sudoedit")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("path", help="print the JSON + env file paths")
    p.set_defaults(func=cmd_path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
