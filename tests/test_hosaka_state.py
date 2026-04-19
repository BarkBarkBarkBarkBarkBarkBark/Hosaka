"""SetupState JSON load compatibility."""

from __future__ import annotations

from hosaka.config.state import SetupState, _LEGACY_KEY_PREFIX, _payload_to_setup_state


def test_legacy_misspelled_keys_migrate_to_picoclaw():
    raw = {
        "setup_completed": True,
        f"{_LEGACY_KEY_PREFIX}enabled": False,
        f"{_LEGACY_KEY_PREFIX}ready": True,
        "picoclaw_enabled": True,
        "unknown_future_field": "x",
    }
    s = _payload_to_setup_state(raw)
    assert s.picoclaw_enabled is True
    assert s.picoclaw_ready is True
    assert s.setup_completed is True


def test_legacy_keys_rename_when_picoclaw_missing():
    raw = {
        f"{_LEGACY_KEY_PREFIX}enabled": False,
        f"{_LEGACY_KEY_PREFIX}ready": False,
    }
    s = _payload_to_setup_state(raw)
    assert s.picoclaw_enabled is False
    assert s.picoclaw_ready is False


def test_extra_json_keys_ignored():
    s = _payload_to_setup_state({"picoclaw_enabled": True, "nonsense": {"a": 1}})
    assert s.picoclaw_enabled is True
    assert isinstance(s, SetupState)
