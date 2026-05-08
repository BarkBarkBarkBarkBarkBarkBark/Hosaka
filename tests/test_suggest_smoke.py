"""Smoke for hosaka.obs.suggest — exact, fuzzy, miss, never-raises."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


def _fresh_with_catalog(tmp_path: Path):
    cat = tmp_path / "features.yaml"
    cat.write_text(
        yaml.safe_dump(
            {
                "features": [
                    {
                        "id": "device.health",
                        "name": "Device Health",
                        "commands": ["/health", "/status"],
                        "baller_command": "/health now",
                    },
                    {
                        "id": "network.wifi",
                        "name": "Wifi",
                        "commands": ["/wifi", "/wifi connect"],
                    },
                    {"id": "obs.events", "name": "Events", "commands": ["/events"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    os.environ["HOSAKA_FEATURES_YAML"] = str(cat)
    for mod in list(sys.modules):
        if mod.startswith("hosaka.obs.suggest"):
            del sys.modules[mod]
    sug = importlib.import_module("hosaka.obs.suggest")
    sug.reset_cache()
    return sug


def test_exact_command_hit(tmp_path):
    sug = _fresh_with_catalog(tmp_path)
    s = sug.suggest_for("/health")
    assert s.feature_id == "device.health"
    assert s.did_you_mean == "/health"
    assert "device.health" in s.manual_url
    assert "known command" in s.message


def test_fuzzy_typo_match(tmp_path):
    sug = _fresh_with_catalog(tmp_path)
    s = sug.suggest_for("/healht")  # typo
    assert s.did_you_mean == "/health"
    assert s.feature_id == "device.health"
    assert "did you mean" in s.message.lower()


def test_total_miss_returns_manual_link(tmp_path):
    sug = _fresh_with_catalog(tmp_path)
    s = sug.suggest_for("/zzzqqq-nothing-like-this")
    # may be a fuzzy near-match or a miss; either way it must have a manual_url and message
    assert s.manual_url
    assert s.message


def test_empty_input_does_not_raise(tmp_path):
    sug = _fresh_with_catalog(tmp_path)
    s = sug.suggest_for("")
    assert s.input == ""
    assert s.manual_url
    assert "manual" in s.message.lower()


def test_known_commands_lists_everything(tmp_path):
    sug = _fresh_with_catalog(tmp_path)
    cmds = sug.known_commands()
    assert "/health" in cmds
    assert "/wifi" in cmds
    assert "/events" in cmds
