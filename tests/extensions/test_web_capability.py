import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hosaka.extensions.manager import Manager
from hosaka.extensions.manifest import ExtensionError, Web


@pytest.mark.parametrize("changes", [
    {"schema_version": True}, {"schema_version": 2}, {"file": "../server.py"},
    {"file": "server.py --port 80"}, {"callable": "app()"}, {"health": "https://example.test/"},
    {"command": "python server.py"},
])
def test_web_contribution_rejects_commands_paths_and_unknown_fields(changes):
    values = {"schema_version": 1, "file": "server.py", "callable": "app", "health": "/health"}
    with pytest.raises(ValidationError):
        Web.model_validate({**values, **changes})


def test_web_approval_is_explicit_separately_digested_and_revocable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOSAKA_DATA_DIR", str(tmp_path / "data"))
    for key in ("SUDO_USER", "HOSAKA_OPERATOR", "HOSAKA_PUBLIC_MODE", "HOSAKA_EXTENSIONS_SAFE_MODE"):
        monkeypatch.delenv(key, raising=False)
    manager = Manager()
    manager.init()
    package = manager.packages / "reference-extension"
    manifest = yaml.safe_load((package / "extension.yaml").read_text())
    manifest["web"] = {"schema_version": 1, "file": "server.py", "callable": "app", "health": "/health"}
    (package / "extension.yaml").write_text(yaml.safe_dump(manifest))
    with pytest.raises(ExtensionError):
        manager.trust("reference-extension", allow_storage=True, allow_web=True)
    source = tmp_path / "web"
    source.mkdir()
    (source / "server.py").write_text("app = None\n")
    manager.trust("reference-extension", allow_storage=True, allow_web=True, web_source=source, web_python=Path(sys.executable))
    approved = manager.registry().extensions["reference-extension"]
    assert "web:self" in approved.grants
    assert approved.web_digest and approved.web_source == str(source)
    manager.revoke("reference-extension")
    revoked = manager.registry().extensions["reference-extension"]
    assert "web:self" not in revoked.grants
    assert revoked.web_digest is None and revoked.web_source is None and revoked.web_python is None
