"""Operator commands for inspecting and switching Hosaka LLM providers."""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, field

from hosaka.llm import llm_config


@dataclass(frozen=True)
class LLMChoice:
    provider: str
    model: str
    base_url: str
    available: bool = True
    settings: dict | None = field(default=None, repr=False)


_selection_choices: list[LLMChoice] | None = None
_OPENAI_MODELS = ("gpt-4.1", "gpt-4.1-mini", "gpt-4o-mini")


def select_llm(argument: str = "") -> int:
    """List numbered choices or select from the last displayed list."""
    global _selection_choices
    if not argument:
        current = llm_config.load()
        profiles = current.get("profiles")
        configs = [current]
        if isinstance(profiles, dict):
            configs.extend(item for item in profiles.values() if isinstance(item, dict))
        openai_models: list[str] = list(_OPENAI_MODELS)
        ollama_models: dict[str, list[str]] = {}
        compatible_choices: list[LLMChoice] = []
        for cfg in configs:
            model = str(cfg.get("model") or "").strip()
            if cfg.get("provider") == "openai" and model and model not in openai_models:
                openai_models.append(model)
            elif cfg.get("provider") in {"openai-compatible", "ollama"}:
                base = str(cfg.get("base_url") or "").rstrip("/")
                if base and model:
                    if (
                        cfg.get("provider") == "ollama"
                        or cfg.get("ollama_discovery")
                        or cfg.get("api_key") == llm_config.OLLAMA_DEFAULT_API_KEY
                    ):
                        ollama_models.setdefault(base, []).append(model)
                    else:
                        compatible_choices.append(
                            LLMChoice("openai-compatible", model, base, settings=dict(cfg))
                        )
        choices = [LLMChoice("openai", model, "https://api.openai.com") for model in openai_models]
        choices.extend(compatible_choices)
        candidates = list(dict.fromkeys([*ollama_models, *llm_config.ollama_discovery_urls()]))
        seen_hosts: set[str] = set()
        for base in candidates:
            host = base.removesuffix("/v1")
            if host in seen_hosts:
                continue
            seen_hosts.add(host)
            result = llm_config.discover_ollama([host], timeout=1.0)
            installed = result["models"] if result else []
            saved = [
                model for url, models in ollama_models.items()
                if url.removesuffix("/v1") == host for model in models
            ]
            for model in dict.fromkeys([*installed, *saved]):
                choices.append(LLMChoice("ollama", model, f"{host}/v1", model in installed))
        _selection_choices = choices
        show()
        print("\nLLM choices:")
        for index, choice in enumerate(choices):
            state = "" if choice.available else " [unavailable: server or model missing]"
            print(f"{index} {choice.provider} {choice.model} — {choice.base_url}{state}")
        if not any(choice.provider == "ollama" and choice.available for choice in choices):
            print("No reachable Ollama server with installed models. Ollama chat is blocked.")
        print("Select with /select llm <number>. OpenAI requires a saved API key.")
        return 0

    if not argument.isascii() or not argument.isdecimal():
        print("Invalid LLM selection. Use /select llm, then /select llm <number>.")
        return 2
    if _selection_choices is None:
        print("List choices first with /select llm, then select a displayed number.")
        return 2
    index = int(argument)
    if index >= len(_selection_choices):
        print("LLM number is out of range. Run /select llm to see the choices.")
        return 2
    choice = _selection_choices[index]
    if choice.provider == "openai":
        return use_openai(choice.model)
    if choice.provider == "openai-compatible":
        if choice.settings is None:
            raise RuntimeError("Saved OpenAI-compatible selection is missing its configuration.")
        config = llm_config.replace_active_config(llm_config.load(), choice.settings)
        llm_config.save(config)
        llm_config.apply_to_env(config)
        print(f"Using {choice.model} at {choice.base_url}. Saved for future starts.")
        return 0
    try:
        result = llm_config.require_ollama(choice.base_url, choice.model)
    except RuntimeError as exc:
        print(exc)
        return 1
    config = llm_config.replace_active_config(llm_config.load(), {
        "provider": "openai-compatible",
        "model": choice.model,
        "base_url": choice.base_url,
        "api_key": llm_config.OLLAMA_DEFAULT_API_KEY,
        "ollama_discovery": True,
        "ollama_models": result["models"],
    })
    llm_config.save(config)
    llm_config.apply_to_env(config)
    print(f"Using Ollama {choice.model} at {choice.base_url}. Saved for future starts.")
    return 0


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
    if current.get("provider") == "openai":
        saved = current
    if isinstance(saved, dict) and saved.get("api_key"):
        config = llm_config.replace_active_config(current, saved)
    else:
        from hosaka.secrets import store

        key = os.getenv("OPENAI_API_KEY", "").strip()
        if not key or key == llm_config.OLLAMA_DEFAULT_API_KEY:
            key = (store.get("OPENAI_API_KEY") or "").strip()
        if not key or key == llm_config.OLLAMA_DEFAULT_API_KEY:
            from hosaka.llm import openai_adapter

            key = openai_adapter._picoclaw_api_key(openai_adapter._load_picoclaw_config()) or ""
            if not key:
                key = store.import_from_picoclaw_security()[0] or ""
        if not key or key == llm_config.OLLAMA_DEFAULT_API_KEY:
            print("No OpenAI key is saved. Run: hosaka secrets set OPENAI_API_KEY")
            return 1
        config = llm_config.replace_active_config(current, {
            "provider": "openai",
            "api_key": key,
            "base_url": "https://api.openai.com",
            "model": llm_config.OPENAI_DEFAULT_MODEL,
        })
    if model:
        config["model"] = model
    config["base_url"] = config.get("base_url") or "https://api.openai.com"
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