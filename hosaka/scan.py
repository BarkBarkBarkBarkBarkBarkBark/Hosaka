"""Offline discovery commands for nearby Hosaka services."""
from __future__ import annotations

import argparse
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from hosaka.llm import llm_config
from hosaka.network.discovery import detect_local_ip


def _lan_candidates() -> list[str]:
    try:
        local_ip = ipaddress.ip_address(detect_local_ip())
    except ValueError:
        return []
    if not local_ip.is_private:
        return []
    network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    return [f"http://{host}:11434" for host in network.hosts() if host != local_ip]


def _has_ollama_port(base_url: str) -> bool:
    host = base_url.removeprefix("http://").removeprefix("https://").split(":", 1)[0]
    try:
        with socket.create_connection((host, 11434), timeout=0.2):
            return True
    except OSError:
        return False


def find_ollama_hosts(candidates: Iterable[str] | None = None) -> list[dict]:
    """Probe known hosts and the active private /24 for Ollama model tags."""
    known = list(candidates or llm_config.ollama_discovery_urls())
    lan = _lan_candidates()
    unique = list(dict.fromkeys(known + lan))
    with ThreadPoolExecutor(max_workers=32) as executor:
        reachable = [url for url, open_port in zip(unique, executor.map(_has_ollama_port, unique)) if open_port]
    found: list[dict] = []
    for url in reachable:
        result = llm_config.discover_ollama([url], timeout=1.5)
        if result:
            found.append(result)
    return found


def _save_result(result: dict, current: dict) -> dict:
    models = result["models"]
    model = str(current.get("model") or "")
    if model not in models:
        model = llm_config.OLLAMA_DEFAULT_MODEL if llm_config.OLLAMA_DEFAULT_MODEL in models else models[0]
    config = llm_config.replace_active_config(current, {
        "provider": "openai-compatible",
        "base_url": f"{result['base_url'].rstrip('/')}/v1",
        "api_key": llm_config.OLLAMA_DEFAULT_API_KEY,
        "model": model,
        "ollama_discovery": True,
        "ollama_models": models,
    })
    llm_config.save(config)
    llm_config.apply_to_env(config)
    return config


def scan_llm(*, use: str | None = None) -> int:
    print("Scanning this local network for Ollama servers...")
    found = find_ollama_hosts()
    if not found:
        print("No Ollama server found. Check that the server and this device share a LAN, then try again.")
        return 1
    for index, result in enumerate(found, start=1):
        print(f"{index}. {result['base_url']}  models: {', '.join(result['models'])}")
    if use is None:
        print("To use the first server now and after reboot: hosaka scan llm --use")
        return 0
    selected = found[0]
    if use != "first":
        selected = next((item for item in found if item["base_url"] == use.rstrip("/")), None)
        if selected is None:
            print(f"Server not found: {use}")
            return 2
    config = _save_result(selected, llm_config.load())
    print(f"Using {config['base_url']} with {config['model']}. Saved for future starts.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hosaka scan")
    commands = parser.add_subparsers(dest="target", required=True)
    llm = commands.add_parser("llm", help="find nearby Ollama servers and their models")
    llm.add_argument("--use", nargs="?", const="first", metavar="URL", help="persist the first result or this URL")
    args = parser.parse_args(argv)
    return scan_llm(use=args.use)


if __name__ == "__main__":
    raise SystemExit(main())