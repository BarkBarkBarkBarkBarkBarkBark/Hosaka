"""Read-only migration inventory. Applying a migration is deliberately unsupported."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hosaka.paths import CORE_ROOT, resolve_paths

MAX_CONFIG_BYTES = 2 * 1024 * 1024


@dataclass
class Credential:
    source: str
    provider: str
    model: str
    value: str = field(repr=False)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _location(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path.absolute()), "status": "missing"}
    try:
        info = path.stat()
    except FileNotFoundError:
        return result
    except OSError:
        return {**result, "status": "unreadable"}
    return {
        **result, "status": "present", "uid": info.st_uid, "gid": info.st_gid,
        "mode": f"{stat.S_IMODE(info.st_mode):04o}",
        "kind": "directory" if stat.S_ISDIR(info.st_mode) else "file",
    }


def inventory() -> dict[str, Any]:
    # These existing helpers only select paths or inspect already-loaded objects.
    # Do not call load(), apply_to_env(), bootstrap, or provider availability checks.
    from hosaka.llm import llm_config, openai_adapter
    from hosaka.secrets import store

    paths = resolve_paths()
    home = paths.operator.home
    sources: dict[str, dict[str, Any]] = {}
    credentials: list[Credential] = []
    profiles: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    def read(source: str, path: Path, kind: str = "json") -> dict[str, Any]:
        metadata = _location(path)
        sources[source] = metadata
        if metadata["status"] == "missing":
            return {}
        if metadata["status"] == "unreadable":
            issues.append({"source": source, "severity": "error", "code": "unreadable"})
            return {}
        try:
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError
            with path.open("rb") as stream:
                raw = stream.read(MAX_CONFIG_BYTES + 1)
            if len(raw) > MAX_CONFIG_BYTES:
                raise ValueError
            text = raw.decode("utf-8")
            if kind == "env":
                from io import StringIO
                from dotenv.parser import parse_stream

                bindings = list(parse_stream(StringIO(text)))
                if any(binding.error for binding in bindings):
                    raise ValueError
                data = {binding.key: binding.value for binding in bindings if binding.key}
            elif kind == "yaml":
                try:
                    import yaml
                except ImportError:
                    metadata["status"] = "parser_unavailable"
                    issues.append({
                        "source": source, "severity": "error",
                        "code": "yaml_parser_unavailable_rerun_dependency_setup",
                    })
                    return {}
                else:
                    try:
                        data = yaml.safe_load(text)
                    except yaml.YAMLError:
                        raise ValueError from None
            else:
                data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError
        except (OSError, ValueError, UnicodeError, RecursionError):
            metadata["status"] = "invalid_or_unreadable"
            issues.append({
                "source": source, "severity": "error", "code": "invalid_or_unreadable",
            })
            return {}
        if metadata["mode"] != "0600":
            issues.append({"source": source, "severity": "warning", "code": "expected_mode_0600"})
        if metadata["uid"] != paths.operator.uid:
            issues.append({"source": source, "severity": "warning", "code": "different_owner"})
        return data

    def credential(source: str, provider: str, model: str, value: object) -> None:
        key = _text(value)
        if key:
            credentials.append(Credential(source, provider, model, key))

    def profile(source: str, config: dict[str, Any], *, pico: bool = False) -> None:
        fields = ("model", "model_name", "api_key") if pico else ("provider", "model", "api_key")
        if any(config.get(name) is not None and not isinstance(config[name], str) for name in fields):
            issues.append({"source": source, "severity": "error", "code": "invalid_profile_fields"})
        if pico and not _text(config.get("model")):
            issues.append({"source": source, "severity": "error", "code": "missing_provider_model"})
        model = _text(config.get("model"))
        provider = model.split("/", 1)[0] if pico and "/" in model else _text(config.get("provider"))
        model = model.split("/", 1)[-1] if pico else model
        profiles.append({
            "source": source, "provider": provider or None, "model": model or None,
            "alias": _text(config.get("model_name")) or None,
            "credential_present": bool(_text(config.get("api_key"))),
        })
        credential(source, provider or "unknown", model or "*", config.get("api_key"))

    def environment(source: str, values: dict[str, Any]) -> None:
        for name, provider in (("OPENAI_API_KEY", "openai"), ("ANTHROPIC_API_KEY", "anthropic")):
            credential(source + ":" + name, provider, "*", values.get(name))

    environment("environment", dict(os.environ))
    secrets_path = store.json_path()
    secrets = read("secrets.selected", secrets_path)
    canonical_secrets = read("secrets.canonical", paths.root / "secrets.json")
    legacy_secrets = read("secrets.legacy", home / ".hosaka/secrets.json")
    reference_sources = {
        "secrets.selected": secrets, "secrets.canonical": canonical_secrets,
        "secrets.legacy": legacy_secrets,
    }
    for source, values in reference_sources.items():
        environment(source, values)
        if any(not isinstance(value, str) for value in values.values()):
            issues.append({"source": source, "severity": "error", "code": "invalid_flat_secret_store"})
        sources[source]["credential_count"] = sum(
            isinstance(value, str) and bool(value.strip())
            for key, value in values.items()
            if key not in {"PICOCLAW_CONFIG_PATH", "PICOCLAW_MODEL"}
        )

    for source, path in (
        ("env.system", store.env_path()),
        ("env.repository", CORE_ROOT / ".env"),
        ("env.user", home / ".hosaka/env"),
    ):
        values = read(source, path, "env")
        environment(source, values)
        reference_sources[source] = values

    llm_path = llm_config._config_file()
    active_llm: dict[str, Any] = {}
    for source, path in (
        ("llm.selected", llm_path), ("llm.user", home / ".hosaka/llm.json"),
        ("llm.system", llm_config._SYSTEM_DIR / "llm.json"),
    ):
        config = read(source, path)
        if source == "llm.selected":
            active_llm = config
        if config:
            profile(source, config)
        saved = config.get("profiles", {})
        if not isinstance(saved, dict):
            issues.append({"source": source, "severity": "error", "code": "invalid_profiles"})
        else:
            for index, saved_config in enumerate(saved.values()):
                if isinstance(saved_config, dict):
                    profile(f"{source}.profile.{index}", saved_config)
                else:
                    issues.append({"source": source, "severity": "error", "code": "invalid_profile"})

    if sources["llm.selected"]["status"] == "missing":
        local_first = os.getenv("HOSAKA_LOCAL_FIRST", "0").strip().lower() in {"1", "true", "yes", "on"}
        active_llm = llm_config.openai_compatible_defaults() if local_first else {
            "provider": "openai", "model": llm_config.OPENAI_DEFAULT_MODEL,
        }
    config_path = openai_adapter._picoclaw_config_path()
    security_path = openai_adapter._picoclaw_security_path()
    pico_paths = {
        "picoclaw.selected": config_path,
        "picoclaw.upstream": home / ".picoclaw/config.json",
        "picoclaw.canonical": paths.root / "picoclaw/config.json",
    }
    references = []
    for source, values in reference_sources.items():
        stored_path = _text(values.get("PICOCLAW_CONFIG_PATH"))
        if stored_path:
            stored = Path(stored_path).expanduser()
            if stored.is_absolute():
                name = "picoclaw.stored" if source == "secrets.selected" else source + ".picoclaw"
                pico_paths[name] = stored
                references.append({
                    "source": source, "config_source": name,
                    "model_alias": _text(values.get("PICOCLAW_MODEL")) or None,
                })
            else:
                issues.append({
                    "source": source, "severity": "error", "code": "relative_stored_picoclaw_path",
                })
    selected_config: dict[str, Any] = {}
    selected_security: dict[str, Any] = {}
    workspaces: dict[str, Any] = {}
    for source, path in pico_paths.items():
        config = read(source, path)
        sidecar = security_path if source == "picoclaw.selected" else path.parent / ".security.yml"
        security = read(source + ".security", sidecar, "yaml")
        if source == "picoclaw.selected":
            selected_config, selected_security = config, security
        if sources[source]["status"] != "present":
            continue
        agents = config.get("agents")
        defaults = agents.get("defaults") if isinstance(agents, dict) else None
        models = config.get("model_list")
        if not isinstance(defaults, dict) or not isinstance(models, list):
            issues.append({"source": source, "severity": "error", "code": "invalid_picoclaw_schema"})
            continue
        if any(defaults.get(name) is not None and not isinstance(defaults[name], str) for name in ("workspace", "model_name")):
            issues.append({"source": source, "severity": "error", "code": "invalid_picoclaw_defaults"})
        sources[source]["version"] = config.get("version") if type(config.get("version")) is int else None
        sources[source]["model_alias"] = _text(defaults.get("model_name")) or None
        workspace = Path(_text(defaults.get("workspace")) or path.parent / "workspace").expanduser()
        if not workspace.is_absolute():
            workspace = path.parent / workspace
        workspaces[source] = {
            name: _location(workspace / name) for name in ("memory", "sessions", "skills")
        }
        workspaces[source]["workspace"] = _location(workspace)
        security_models = security.get("model_list", {})
        if not isinstance(security_models, dict):
            issues.append({"source": source + ".security", "severity": "error", "code": "invalid_security_schema"})
            security_models = {}
        known_aliases = {
            _text(entry.get("model_name")) for entry in models if isinstance(entry, dict)
        }
        sources[source + ".security"]["unmapped_model_entries"] = sum(
            not isinstance(name, str) or name.split(":", 1)[0] not in known_aliases
            for name in security_models
        )
        sources[source + ".security"]["credential_count"] = 0
        for record in security_models.values():
            if not isinstance(record, dict):
                issues.append({"source": source + ".security", "severity": "error", "code": "invalid_security_entry"})
                continue
            keys = record.get("api_keys", [])
            if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
                issues.append({"source": source + ".security", "severity": "error", "code": "invalid_api_keys"})
                continue
            sources[source + ".security"]["credential_count"] += sum(bool(key.strip()) for key in keys)
            sources[source + ".security"]["credential_count"] += bool(_text(record.get("api_key")))
        for index, entry in enumerate(models):
            if not isinstance(entry, dict):
                issues.append({"source": source, "severity": "error", "code": "invalid_model"})
                continue
            model_source = f"{source}.model.{index}"
            profile(model_source, entry, pico=True)
            alias = _text(entry.get("model_name"))
            for name, record in security_models.items():
                if not isinstance(name, str) or name.split(":", 1)[0] != alias or not isinstance(record, dict):
                    continue
                keys = record.get("api_keys", [])
                if not isinstance(keys, list):
                    issues.append({"source": source + ".security", "severity": "error", "code": "invalid_api_keys"})
                    continue
                meta = profiles[-1]
                for key in [*keys, record.get("api_key")]:
                    credential(
                        model_source + ".security", meta["provider"] or "unknown",
                        meta["model"] or "*", key,
                    )
                meta["credential_present"] |= any(_text(key) for key in [*keys, record.get("api_key")])

    groups: dict[tuple[str, str], list[Credential]] = {}
    for candidate in credentials:
        if candidate.model != "*":
            groups.setdefault((candidate.provider, candidate.model), []).append(candidate)
    for candidate in credentials:
        if candidate.model == "*":
            matching = [scope for scope in groups if scope[0] == candidate.provider]
            for scope in matching or [(candidate.provider, "*")]:
                groups.setdefault(scope, []).append(candidate)
    conflicts = []
    for (provider, model), candidates in sorted(groups.items()):
        by_source: dict[str, set[str]] = {}
        for candidate in candidates:
            by_source.setdefault(candidate.source, set()).add(candidate.value)
        if any(not left.intersection(right) for left in by_source.values() for right in by_source.values()):
            conflicts.append({
                "kind": "credential_candidates_differ", "provider": provider, "model": model,
                "sources": sorted(by_source), "requires_operator_choice": True,
            })

    # Reflect the current adapter's precedence without loading fallbacks or
    # hydrating the process. In a TUI, environment values may already be hydrated.
    winning_source = None
    for source, value in (
        ("environment:OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
        ("llm.selected" if sources["llm.selected"]["status"] == "present"
         else "openai-compatible default", active_llm.get("api_key")),
        ("picoclaw.selected", openai_adapter._picoclaw_api_key(selected_config)),
        ("picoclaw.selected.security",
         openai_adapter._picoclaw_security_api_key(selected_config, selected_security)),
    ):
        if _text(value):
            winning_source = source
            break
    base = (
        _text(os.getenv("OPENAI_BASE_URL")) or _text(active_llm.get("base_url"))
        or openai_adapter._OPENAI_DEFAULT_BASE
    ).rstrip("/")
    if winning_source is None and base != openai_adapter._OPENAI_DEFAULT_BASE:
        winning_source = "openai-compatible default"
    model = _text(os.getenv("OPENAI_MODEL")) or _text(active_llm.get("model"))
    if not model:
        model = (
            os.getenv("HOSAKA_OLLAMA_MODEL", llm_config.OLLAMA_DEFAULT_MODEL)
            if base != openai_adapter._OPENAI_DEFAULT_BASE else llm_config.OPENAI_DEFAULT_MODEL
        )
    proposed = {
        name: paths.as_dict()["paths"][name]
        for name in ("config", "secrets", "providers", "picoclaw_config", "picoclaw_workspace")
    }
    effective_workspace = workspaces.get("picoclaw.selected", {}).get("workspace")
    workspace_override = os.getenv("HOSAKA_WORKSPACE")
    if workspace_override:
        effective_workspace = _location(Path(workspace_override).expanduser().resolve())
    return {
        "schema_version": 1, "dry_run": True, "apply_supported": False,
        "provider_request_verified": False,
        "context": "current_process_without_bootstrap",
        "context_note": "Environment may already be hydrated by a TUI/service; source provenance before hydration is unknown. Environment files and stored profile references are inventoried, not applied.",
        "operator": paths.as_dict()["operator"],
        "effective": {
            "runtime_home": str(Path.home()), "data_root": str(paths.root),
            "secrets": str(secrets_path), "llm_config": str(llm_path),
            "picoclaw_config": str(config_path), "picoclaw_security": str(security_path),
            "picoclaw_model_override": _text(os.getenv("PICOCLAW_MODEL")) or None,
            "picoclaw_default_model_alias": sources["picoclaw.selected"].get("model_alias"),
            "console_selection": "picoclaw_model_override" if _text(os.getenv("PICOCLAW_MODEL")) else "hosaka_console_overlay",
            "openai_model": model,
            "llm_config_present": sources["llm.selected"]["status"] == "present",
            "openai_credential_source": winning_source,
            "credential_resolution_complete": not any(issue["severity"] == "error" for issue in issues),
            "workspace": effective_workspace,
        },
        "proposed": proposed, "sources": sources, "profiles": profiles,
        "stored_profile_references": references,
        "canonical_metadata": {
            name: _location(Path(proposed[name])) for name in ("config", "providers")
        },
        "credential_sources": sorted({candidate.source for candidate in credentials}),
        "workspaces": workspaces, "conflicts": conflicts, "issues": issues,
        "status": "blocked" if any(issue["severity"] == "error" for issue in issues)
        else "needs_review" if conflicts else "inventoried",
        "proposed_actions": [
            "Review effective paths, stored profile references and redacted conflicts.",
            "Choose credential/profile imports explicitly; preserve upstream PicoClaw models and workspace.",
            "Back up protected files before a future versioned, atomic migration.",
            "Coordinate launcher/service paths and remove normal root bootstrap before switching ownership.",
            "Retain legacy files; this command cannot apply changes.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inventory()
    except (OSError, ValueError, RecursionError):
        print("Hosaka migration inventory failed: invalid or unreadable path configuration; run hosaka paths to diagnose.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Hosaka migration inventory: {report['status']} (read-only; no provider request)")
        print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["status"] == "blocked" else 2 if report["conflicts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
