from __future__ import annotations

import json
import sys
from unittest.mock import Mock

from hosaka import games


def test_run_play_uses_json_module_command(monkeypatch) -> None:
    process = Mock()
    process.communicate.return_value = (json.dumps({"ok": True, "action": "list", "games": []}), "")
    process.returncode = 0
    popen = Mock(return_value=process)
    monkeypatch.setattr(games.subprocess, "Popen", popen)

    result = games.run_play("list", "psx")

    assert result == {"ok": True, "action": "list", "games": []}
    assert popen.call_args.args[0] == [sys.executable, "-m", "hosaka.play", "--json", "list", "psx"]