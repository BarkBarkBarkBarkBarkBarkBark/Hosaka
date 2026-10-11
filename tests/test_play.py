from __future__ import annotations

import json
import signal
from pathlib import Path

import pytest

from hosaka import play, main_console


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "roms/psx"
    root.mkdir(parents=True)
    for name in ("Spyro the Dragon.cue", "Spyro the Dragon.bin", "Spyro the Dragon.chd",
                 "Crash Bandicoot.cue", "Crash Team Racing.chd", "cover.png", "memory.srm"):
        (root / name).touch()
    monkeypatch.setenv("HOSAKA_PSX_ROMS", str(root))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return root


def test_catalog_is_psx_and_deduplicates_disc_tracks(library):
    assert [p.name for p in play.catalog()] == ["Crash Bandicoot.cue", "Crash Team Racing.chd", "Spyro the Dragon.cue"]


def test_exact_and_fuzzy_names(library, monkeypatch):
    monkeypatch.setattr(play, "launch", lambda rom: {"ok": True, "title": rom.stem, "action": "launch"})
    assert play.execute(["spyro"])["title"] == "Spyro the Dragon"
    assert play.execute(["Crash Bandicoot"])["title"] == "Crash Bandicoot"
    payload = play.execute(["crash"])
    assert payload["ok"] is False
    assert payload["action"] == "ambiguous"
    assert [g["title"] for g in payload["matches"]] == ["Crash Bandicoot", "Crash Team Racing"]


def test_missing_library_is_an_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOSAKA_PSX_ROMS", str(tmp_path / "missing"))
    assert play.main(["--json", "list", "psx"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "HOSAKA_PSX_ROMS" in payload["error"]


def test_json_ambiguity_returns_choices(library, capsys):
    assert play.main(["--json", "crash"]) == 2
    assert len(json.loads(capsys.readouterr().out)["matches"]) == 2


def test_empty_library_is_not_simulated(library):
    for file in library.iterdir():
        file.unlink()
    assert play.execute([])["games"] == []


def test_configurable_core_and_rom_path_are_separate_arguments(library, tmp_path, monkeypatch):
    core = tmp_path / "PSX Core.so"
    core.touch()
    config = tmp_path / "retroarch.cfg"
    config.touch()
    monkeypatch.setenv("HOSAKA_PSX_CORE", str(core))
    monkeypatch.setenv("HOSAKA_RETROARCH", "/usr/bin/retroarch")
    monkeypatch.setenv("HOSAKA_RETROARCH_CONFIG", str(config))
    rom = library / "Spyro the Dragon.cue"
    assert play.launch_argv(rom) == ["/usr/bin/retroarch", "-L", str(core), "--config", str(config), str(rom)]


def test_retropie_config_is_parsed_without_a_shell(library, tmp_path, monkeypatch):
    config = tmp_path / "emulators.cfg"
    exe = tmp_path / "retroarch"
    exe.touch()
    core = tmp_path / "core.so"
    core.touch()
    config.write_text(f'lr-pcsx-rearmed = "{exe} --verbose -L {core} --config /config/psx.cfg %ROM%"\ndefault = "lr-pcsx-rearmed"\n')
    monkeypatch.delenv("HOSAKA_PSX_CORE", raising=False)
    original = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda self: True if str(self) == "/opt/retropie/configs/psx/emulators.cfg" else original(self))
    original_read = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: config.read_text() if str(self) == "/opt/retropie/configs/psx/emulators.cfg" else original_read(self, *a, **k))
    rom = library / "Spyro the Dragon.cue"
    assert play.launch_argv(rom) == [str(exe), "--verbose", "-L", str(core), "--config", "/config/psx.cfg", str(rom)]


def test_stop_never_signals_a_reused_pid(library, monkeypatch):
    state = play.state_file()
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"pid": 100, "identity": "old"}))
    monkeypatch.setattr(play, "process_identity", lambda pid: "new")
    monkeypatch.setattr(play.os, "kill", lambda *a: pytest.fail("must not signal a reused PID"))
    assert play.stop()["ok"] is True
    assert not state.exists()

@pytest.mark.parametrize("saved", [[], {"pid": -1, "identity": "x"}, {"pid": 100}])
def test_invalid_state_is_reported_without_signaling(library, monkeypatch, capsys, saved):
    state = play.state_file()
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps(saved))
    monkeypatch.setattr(play.os, "kill", lambda *a: pytest.fail("must not signal invalid state"))
    assert play.main(["--json", "stop"]) == 1
    assert "Invalid Hosaka emulator state" in json.loads(capsys.readouterr().out)["error"]


def test_stop_signals_only_recorded_emulator(library, monkeypatch):
    state = play.state_file()
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"pid": 100, "identity": "matching"}))
    identities = iter(["matching", ""])
    monkeypatch.setattr(play, "process_identity", lambda pid: next(identities))
    calls = []
    monkeypatch.setattr(play.os, "kill", lambda *args: calls.append(args))
    assert play.stop()["ok"] is True
    assert calls == [(100, signal.SIGTERM)]


def test_existing_legacy_game_is_not_interrupted(library, monkeypatch):
    monkeypatch.setattr(play, "launch_argv", lambda rom: ["retroarch", str(rom)])
    monkeypatch.setattr(play, "graphical_env", lambda: {})
    monkeypatch.setattr(play, "other_retroarch_pids", lambda: [123])
    monkeypatch.setattr(play.subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch another emulator"))
    with pytest.raises(RuntimeError, match="already running"):
        play.launch(library / "Spyro the Dragon.cue")

@pytest.mark.parametrize("exit_code", [None, 1])
def test_launch_confirmation_and_audio_recovery(library, monkeypatch, exit_code):
    class Process:
        pid = 123
        returncode = exit_code

        def poll(self):
            return self.returncode

    signals, commands = [], []
    monkeypatch.setattr(play, "launch_argv", lambda rom: ["retroarch", str(rom)])
    monkeypatch.setattr(play, "graphical_env", lambda: {"DISPLAY": ":0"})
    monkeypatch.setattr(play, "other_retroarch_pids", lambda: [])
    monkeypatch.setattr(play, "signal_voice", signals.append)
    monkeypatch.setattr(play, "process_identity", lambda _: "identity")
    monkeypatch.setattr(play.time, "sleep", lambda _: None)
    monkeypatch.setattr(play.subprocess, "Popen", lambda argv, **kwargs: commands.append((argv, kwargs)) or Process())
    if exit_code is None:
        result = play.launch(library / "Spyro the Dragon.cue")
        assert result == {"ok": True, "action": "launch", "system": "psx", "title": "Spyro the Dragon", "pid": 123}
        assert json.loads(play.state_file().read_text())["identity"] == "identity"
        assert signals == [signal.SIGUSR1]
    else:
        with pytest.raises(RuntimeError, match="status 1"):
            play.launch(library / "Spyro the Dragon.cue")
        assert signals == [signal.SIGUSR1, signal.SIGUSR2]
        assert not play.state_file().exists()
    assert commands[0][1]["start_new_session"] is True
    assert commands[0][1]["env"] == {"DISPLAY": ":0"}


@pytest.mark.parametrize("command,args", [
    ("/play", ()), ("/play spyro", ("spyro",)), ("/play list psx", ("list", "psx")),
    ("/play Spyro the Dragon (USA)", ("Spyro the Dragon (USA)",)), ("/play stop", ("stop",)),
])
def test_slash_play_bypasses_llm(monkeypatch, capsys, tmp_path, command, args):
    from hosaka import games
    calls = []
    monkeypatch.setattr(games, "run_play", lambda *a, **k: calls.append(a) or {"ok": True, "action": "stop", "message": "done"})
    monkeypatch.setattr(main_console, "one_shot", lambda *a: pytest.fail("must not dispatch game command to LLM"))
    assert main_console._dispatch_command(command, tmp_path, "llm") == (tmp_path, "llm")
    assert calls == [args]
    assert "done" in capsys.readouterr().out
