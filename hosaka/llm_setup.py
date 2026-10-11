"""Hidden-key setup for a named PicoClaw provider profile."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from hosaka.secrets import store


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".setup-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def configure(provider: str, model: str, api_base: str | None, key: str) -> Path:
    from hosaka.llm.openai_adapter import _picoclaw_config_path

    original = _picoclaw_config_path()
    try:
        config = json.loads(original.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read PicoClaw config at {original}. Run picoclaw onboard or reinstall Hosaka.") from exc
    if not isinstance(config, dict):
        raise ValueError("PicoClaw configuration must be a JSON object.")
    agents = config.get("agents")
    defaults = agents.get("defaults") if isinstance(agents, dict) else None
    if not isinstance(defaults, dict):
        raise ValueError("PicoClaw configuration is missing agents.defaults.")
    if not model.strip() or any(char.isspace() for char in model):
        raise ValueError("Use a model ID with no whitespace.")
    if api_base:
        url = urlparse(api_base)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("API base must be an HTTP(S) URL without embedded credentials.")
    if provider == "openai-compatible" and not api_base:
        raise ValueError("OpenAI-compatible providers require --api-base.")
    workspace = Path(str(defaults.get("workspace") or original.parent / "workspace")).expanduser()
    if not workspace.is_absolute():
        workspace = original.parent / workspace
    defaults["workspace"] = str(workspace)
    defaults["model_name"] = "hosaka-user"
    entry = {
        "model_name": "hosaka-user",
        "model": f"{'openai' if provider == 'openai-compatible' else provider}/{model}",
    }
    if api_base:
        entry["api_base"] = api_base
    config["model_list"] = [entry]
    profile = store.json_path().parent / "picoclaw" / "config.json"
    if config.get("version", 0) >= 3:
        security = "model_list:\n  hosaka-user:0:\n    api_keys:\n      - " + json.dumps(key) + "\n"
        write_private(profile.parent / ".security.yml", security)
    else:
        entry["api_key"] = key
    write_private(profile, json.dumps(config, indent=2) + "\n")
    values = store.load()
    values["PICOCLAW_CONFIG_PATH"] = str(profile)
    values["PICOCLAW_MODEL"] = "hosaka-user"
    store.save(values, mirror=False)
    return profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["openai", "anthropic", "openai-compatible"], required=True)
    parser.add_argument("--model", required=True, help="provider model ID, without the provider/ prefix")
    parser.add_argument("--api-base", help="required for OpenAI-compatible endpoints")
    parser.add_argument("--no-key", action="store_true", help="local endpoint that does not require a key")
    args = parser.parse_args(argv)
    if args.no_key and args.provider != "openai-compatible":
        parser.error("--no-key is only supported for local OpenAI-compatible endpoints")
    if not args.no_key and not sys.stdin.isatty():
        print("API-key setup requires a real terminal for hidden input. Run hosaka configure llm from your shell.", file=sys.stderr)
        return 2
    key = "" if args.no_key else getpass.getpass(f"{args.provider} API key (hidden): ")
    if not args.no_key and not key.strip():
        print("API key cannot be empty.", file=sys.stderr)
        return 2
    try:
        path = configure(args.provider, args.model, args.api_base, key.strip())
    except (ValueError, OSError) as exc:
        print(f"Provider setup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {args.provider}/{args.model} to a private PicoClaw profile at {path}.")
    print("Restart hosaka tui to use it. No model request was sent; verify access with /llm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
