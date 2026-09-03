"""Operator commands for inspecting and switching Hosaka LLM providers."""
from __future__ import annotations

import argparse
import os

from hosaka.llm import llm_config


def show() -> int:
    config = llm_config.load()
    print(f"Provider: {config.get('provider', 'not configured')}")
    print(f"Model:    {config.get('model', 'not configured')}")
    print(f"Endpoint: {config.get('base_url', 'default')}")
    profiles = config.get("profiles")
    if isinstance(profiles, dict) and profiles:
        print(f"Saved:    {', '.join(sorted(profiles))}")
    return 0


def use_openai(model: str | None = None) -> int:
    current = llm_config.load()
    profiles = current.get("profiles")
    saved = profiles.get("openai") if isinstance(profiles, dict) else None
    if isinstance(saved, dict) and saved.get("api_key"):
        config = llm_config.replace_active_config(current, saved)
    else:
        from hosaka.secrets import store

        store.apply_to_env()
        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key or key == llm_config.OLLAMA_DEFAULT_API_KEY:
            print("No OpenAI key is saved. Run: hosaka secrets set OPENAI_API_KEY")
            return 1
        config = llm_config.replace_active_config(current, {
            "provider": "openai",
            "api_key": key,
            "base_url": "https://api.openai.com",
            "model": "gpt-4o-mini",
        })
    if model:
        config["model"] = model
    llm_config.save(config)
    llm_config.apply_to_env(config)
    print(f"Using OpenAI {config['model']}. Saved for future starts.")
    return 0


def use_ollama(use: str | None) -> int:
    from hosaka.scan import scan_llm

    return scan_llm(use=use)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hosaka llm")
    commands = parser.add_subparsers(dest="provider")
    commands.add_parser("status", aliases=["list"], help="show the active provider, model, and endpoint")
    openai = commands.add_parser("openai", help="switch to the saved OpenAI profile")
    openai.add_argument("model", nargs="?", help="optional OpenAI model name")
    ollama = commands.add_parser("ollama", aliases=["local"], help="scan for and select local Ollama")
    ollama.add_argument("--use", nargs="?", const="first", metavar="URL", help="persist the first result or this URL")
    scan = commands.add_parser("scan", help="find nearby Ollama servers and their models")
    scan.add_argument("--use", nargs="?", const="first", metavar="URL", help="persist the first result or this URL")
    args = parser.parse_args(argv)
    if args.provider in (None, "status", "list"):
        return show()
    if args.provider == "openai":
        return use_openai(args.model)
    return use_ollama(args.use)


if __name__ == "__main__":
    raise SystemExit(main())