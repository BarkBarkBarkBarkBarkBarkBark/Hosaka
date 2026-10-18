#!/usr/bin/env bash
# Optional live integration: HOSAKA_IMAGE=local-image bash tests/test_container_runtime.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
temp="$(mktemp -d)"
TEST_NODE_ID=""
cleanup() {
    if [[ -n "$TEST_NODE_ID" ]]; then
        docker rm -f "$TEST_NODE_ID" >/dev/null 2>&1 || true
    fi
    docker run --rm --mount "type=bind,src=$temp,dst=/test" --entrypoint /bin/rm \
        "$HOSAKA_IMAGE" -rf /test/runtime
    rm -rf "$temp"
}
trap cleanup EXIT
mkdir -p "$temp/project"
printf 'host-data\n' >"$temp/project/input.txt"
ln -s "$temp/outside.txt" "$temp/project/outside-link"
printf 'not shared\n' >"$temp/outside.txt"
export HOSAKA_HOME="$temp/runtime"
export HOSAKA_CONTAINER="hosaka-test-$$"
cli() { bash "$root/install/bin/hosaka" "$@"; }
cli workspace "$temp/project"
cli paths --json >"$temp/paths.json"
cli extensions list --json >"$temp/extensions.json"
python3 - "$temp/extensions.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
reference = next(item for item in report["extensions"] if item["id"] == "reference-extension")
assert reference["enabled"] is False and reference["grants"] == []
assert not report["execution_available"] and not report["ui_available"]
PY
python3 - "$temp/paths.json" "$root" "$HOSAKA_HOME" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
assert report["installation"]["mode"] == "docker"
assert report["paths"]["extensions"] == "/root/.hosaka/extensions"
assert report["paths"]["games"] == "/root/.hosaka/games"
host = Path(sys.argv[3]).resolve()
assert not host.is_relative_to(Path(sys.argv[2]).resolve())
for name in ("extensions", "extension-data", "state", "logs", "games/roms/psx"):
    assert (host / "runtime" / name).is_dir(), name
PY
cli extensions create qualification-demo --json >"$temp/qualification-package.json"
printf 'owner-edited package\n' >"$HOSAKA_HOME/runtime/extensions/qualification-demo/owner.txt"
cli shell <<'SH'
set -e
/opt/hosaka-field-terminal/.venv/bin/python - <<'PY'
import hashlib
from pathlib import Path
from hosaka.paths import offline_report, resolve_paths

paths = resolve_paths()
assert all(directory.is_dir() for directory in paths.directories().values())
assert not paths.root.is_relative_to(Path("/opt/hosaka-field-terminal"))
assert (paths.root / "extensions/qualification-demo/owner.txt").read_text() == "owner-edited package\n"
data = paths.root / "extension-data/qualification-demo"
data.mkdir(exist_ok=True)
(data / "receipt.txt").write_text("persisted across container replacement\n")
(data / "core-digest.txt").write_text(hashlib.sha256(Path("/opt/hosaka-field-terminal/hosaka/paths.py").read_bytes()).hexdigest())
assert not any(check["status"] == "fail" for check in offline_report()["checks"])
PY
SH
cli shell <<'SH'
set -e
/opt/hosaka-field-terminal/.venv/bin/python - <<'PY'
import hashlib
from pathlib import Path
from hosaka.paths import resolve_paths

paths = resolve_paths()
data = paths.root / "extension-data/qualification-demo"
assert (data / "receipt.txt").read_text() == "persisted across container replacement\n"
assert (paths.root / "extensions/qualification-demo/owner.txt").read_text() == "owner-edited package\n"
assert (data / "core-digest.txt").read_text() == hashlib.sha256(Path("/opt/hosaka-field-terminal/hosaka/paths.py").read_bytes()).hexdigest()
PY
SH
export HOSAKA_PORT=0
cli up
TEST_NODE_ID="$(docker inspect --format '{{.Id}}' "$HOSAKA_CONTAINER")"
port="$(docker port "$HOSAKA_CONTAINER" 8421/tcp)"
python3 - "${port##*:}" "$HOSAKA_CONTAINER" <<'PY'
import json
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

base = f"http://127.0.0.1:{sys.argv[1]}"
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    try:
        with urlopen(base + "/api/health", timeout=3) as response:
            health = json.load(response)
        if health.get("web") == "ok" and health.get("ui_built") is True:
            status = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", sys.argv[2]], text=True).strip()
            if status == "healthy":
                break
    except (URLError, TimeoutError, OSError):
        pass
    time.sleep(1)
else:
    raise SystemExit("Container did not serve a built UI and pass its real Docker healthcheck.")
with urlopen(base + "/build-stamp.json", timeout=3) as response:
    stamp = json.load(response)
assert stamp["sha"] == health["commit"]
print("Default image entrypoint, built UI, build stamp and Docker healthcheck verified.")
PY
cli doctor --offline --strict --json >"$temp/doctor.json"
cli migrate --dry-run --json >"$temp/running-inventory.json"
python3 - "$temp/running-inventory.json" <<'PY'
import json
import sys
from pathlib import Path

assert json.loads(Path(sys.argv[1]).read_text())["dry_run"] is True
PY
cli down
TEST_NODE_ID=""
python3 - "$HOSAKA_HOME" "$temp/inventory-before.json" <<'PY'
import json
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
snapshot = {
    str(path.relative_to(root)): [stat.S_IMODE(path.stat().st_mode), path.read_bytes().hex() if path.is_file() else None]
    for path in [root, *root.rglob("*")]
}
Path(sys.argv[2]).write_text(json.dumps(snapshot))
PY
cli migrate --dry-run --json >"$temp/inventory.json"
python3 - "$HOSAKA_HOME" "$temp/inventory-before.json" "$temp/inventory.json" <<'PY'
import json
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
snapshot = {
    str(path.relative_to(root)): [stat.S_IMODE(path.stat().st_mode), path.read_bytes().hex() if path.is_file() else None]
    for path in [root, *root.rglob("*")]
}
assert snapshot == json.loads(Path(sys.argv[2]).read_text())
report = json.loads(Path(sys.argv[3]).read_text())
assert report["dry_run"] is True and report["apply_supported"] is False
assert report["effective"]["picoclaw_config"] == "/root/.picoclaw/config.json"
assert report["proposed"]["picoclaw_config"] == "/root/.hosaka/picoclaw/config.json"
assert not report["provider_request_verified"]
PY
docker run --rm --read-only --network none -e HOME=/tmp/empty-inventory-home \
    "$HOSAKA_IMAGE" migrate --dry-run --json >"$temp/empty-inventory.json"
python3 - "$temp/empty-inventory.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
assert report["sources"]["picoclaw.selected"]["status"] == "missing"
assert report["sources"]["secrets.selected"]["status"] == "missing"
PY
cli configure llm --provider openai-compatible --model test-model --api-base http://localhost:11434/v1 --no-key
cli shell <<'SH'
set -e
test "$PWD" = /workspace
test "$HOSAKA_PROJECT_DIR" = /workspace
grep -q host-data input.txt
if touch must-not-write 2>/dev/null; then exit 1; fi
test ! -r outside-link
/opt/hosaka-field-terminal/.venv/bin/python - <<'PY'
from hosaka.secrets import store
from pathlib import Path
import json
store.apply_to_env()
assert store.get("PICOCLAW_MODEL") == "hosaka-user"
path = Path(store.get("PICOCLAW_CONFIG_PATH"))
assert path.stat().st_mode & 0o777 == 0o600
assert json.loads(path.read_text())["model_list"][0]["model"] == "openai/test-model"
from hosaka.llm import picoclaw_adapter
native_chat = picoclaw_adapter.chat_sync
def inspect_overlay(*args, **kwargs):
    config = json.loads((Path(kwargs["env"]["PICOCLAW_HOME"]) / "config.json").read_text())
    assert config["agents"]["defaults"]["workspace"] == "/root/.picoclaw/workspace"
    assert "Operator project directory: /workspace" in args[0]
    assert kwargs["model"] == "hosaka-user"
    return "ok"
picoclaw_adapter.chat_sync = inspect_overlay
assert "".join(picoclaw_adapter.console_chat_stream([{"role": "user", "content": "hello"}])) == "ok"
picoclaw_adapter.chat_sync = native_chat
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
class LocalProvider(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert request["model"] == "test-model"
        results = [message for message in request["messages"] if message.get("role") == "tool"]
        if results:
            assert any("host-data" in str(message.get("content", "")) for message in results), results
            message = {"role": "assistant", "content": "container-provider-ok"}
            finish = "stop"
        else:
            message = {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "read-test", "type": "function",
                                "function": {"name": "read_file",
                                             "arguments": json.dumps({"path": "/workspace/input.txt"})}}],
            }
            finish = "tool_calls"
        payload = json.dumps({
            "id": "test", "object": "chat.completion", "created": 0, "model": "test-model",
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def log_message(self, *args):
        pass
server = HTTPServer(("127.0.0.1", 0), LocalProvider)
Thread(target=server.serve_forever, daemon=True).start()
config = json.loads(path.read_text())
config["model_list"][0]["api_base"] = f"http://127.0.0.1:{server.server_port}/v1"
path.write_text(json.dumps(config))
try:
    reply = "".join(picoclaw_adapter.console_chat_stream([{"role": "user", "content": "hello"}], timeout=30))
    assert "container-provider-ok" in reply, reply
finally:
    server.shutdown()
PY
SH
cli workspace "$temp/project" --read-write
cli shell <<'SH'
set -e
echo container-edit >written.txt
SH
grep -q container-edit "$temp/project/written.txt"
cli workspace clear
cli shell <<'SH'
set -e
echo persisted >persistent.txt
SH
cli shell <<'SH'
set -e
grep -q persisted persistent.txt
SH
echo "Container runtime, external directories and replacement-persistence integration tests passed"
