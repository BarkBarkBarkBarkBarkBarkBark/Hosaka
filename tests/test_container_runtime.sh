#!/usr/bin/env bash
# Optional live integration: HOSAKA_IMAGE=local-image bash tests/test_container_runtime.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
temp="$(mktemp -d)"
cleanup() {
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
echo "Container runtime integration tests passed"
