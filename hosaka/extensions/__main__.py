from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hosaka.extensions.manager import Manager
from hosaka.extensions.manifest import ExtensionError, validate_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extension authoring and explicitly approved trusted-local execution (not sandboxed).")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "list", "doctor"):
        command = commands.add_parser(name)
        command.add_argument("--json", action="store_true")
    for name in ("info", "enable", "disable", "remove", "revoke"):
        command = commands.add_parser(name)
        command.add_argument("id")
        command.add_argument("--json", action="store_true")
    command = commands.add_parser("trust")
    command.add_argument("id")
    command.add_argument("--trusted-local", action="store_true", required=True, help="Approve current source to run with your user privileges; NOT sandboxed")
    command.add_argument("--allow-storage", action="store_true", help="Grant only this extension's data capability")
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("run")
    command.add_argument("id")
    command.add_argument("action")
    command.add_argument("--params", default="{}", help="JSON object; never pass provider credentials")
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("cancel")
    command.add_argument("id")
    command.add_argument("invocation_id")
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("safe-mode")
    command.add_argument("setting", choices=["on", "off", "status"])
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("create")
    command.add_argument("id")
    command.add_argument("--path", type=Path, help="New external working-copy directory")
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("link")
    command.add_argument("path", type=Path)
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("validate")
    command.add_argument("target", help="Installed ID or existing package directory")
    command.add_argument("--json", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    try:
        if os.getenv("HOSAKA_PUBLIC_MODE", "").lower() in {"1", "true", "yes", "on"}:
            raise ExtensionError("Extension authoring is unavailable in public/hosted mode.")
        manager = Manager()
        if args.command == "init":
            result = manager.init()
        elif args.command == "list":
            result = manager.discover()
        elif args.command == "doctor":
            result = manager.doctor()
        elif args.command == "create":
            result = manager.create(args.id, args.path)
        elif args.command == "link":
            result = manager.link(args.path)
        elif args.command == "validate":
            path = Path(args.target).expanduser()
            if not path.is_dir():
                path = Path(manager.info(args.target)["path"])
            package = validate_package(path)
            result = {"valid": True, "id": package.manifest.id, "path": str(package.root)}
        elif args.command in {"enable", "disable"}:
            result = manager.enable(args.id, args.command == "enable")
        elif args.command == "remove":
            result = manager.remove(args.id)
        elif args.command == "trust":
            result = manager.trust(args.id, allow_storage=args.allow_storage)
        elif args.command == "revoke":
            result = manager.revoke(args.id)
        elif args.command == "safe-mode":
            result = manager.safe_mode(args.setting)
        elif args.command == "run":
            from hosaka.extensions.runner import run

            result = run(manager, args.id, args.action, json.loads(args.params))
        elif args.command == "cancel":
            from hosaka.extensions.runner import cancel

            cancel(manager, args.id, args.invocation_id)
            result = {"cancel_requested": True, "invocation_id": args.invocation_id}
        else:
            result = manager.info(args.id)
    except (OSError, ExtensionError, ValueError, RecursionError) as exc:
        print(f"Extensions failed: {ascii(str(exc))[1:-1]}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True))
    if args.command == "init" and result.get("errors"):
        print("Extension bootstrap completed; invalid packages were preserved and skipped. Run hosaka extensions doctor.", file=sys.stderr)
        return 0
    return 1 if result.get("errors") or result.get("status") == "fail" or result.get("ok") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
