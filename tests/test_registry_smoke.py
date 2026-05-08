"""Smoke for hosaka.obs.registry — @feature, @subfeature, hydrate, reconcile."""
from __future__ import annotations

import importlib
import os
import sys

import pytest


def _fresh():
    """Fresh hosaka.obs + registry with obs disabled (we just test registration)."""
    for k in [k for k in os.environ if k.startswith("HOSAKA_OBS")]:
        del os.environ[k]
    os.environ["HOSAKA_OBS"] = "off"  # don't fire writer
    for mod in list(sys.modules):
        if mod.startswith("hosaka.obs"):
            del sys.modules[mod]
    obs = importlib.import_module("hosaka.obs")
    reg = importlib.import_module("hosaka.obs.registry")
    reg.clear()
    return obs, reg


def test_feature_decorator_registers_and_wraps():
    _, reg = _fresh()

    @reg.feature(
        "test.alpha",
        name="Alpha",
        category="testing",
        owner="qa",
        status="stable",
        commands=["/alpha"],
        baller_command="/alpha now",
        why_you_care="alpha matters",
    )
    def alpha(x):
        return x * 2

    assert alpha(3) == 6
    assert getattr(alpha, "__hosaka_feature_id__", None) == "test.alpha"

    rec = reg.get("test.alpha")
    assert rec is not None
    assert rec.name == "Alpha"
    assert rec.commands == ["/alpha"]
    assert rec.baller_command == "/alpha now"
    assert rec.source == "code"
    assert rec.callable_qualname and "alpha" in rec.callable_qualname


def test_subfeature_inherits_parent_metadata():
    _, reg = _fresh()

    @reg.feature("net.wifi", category="network", owner="net-team", status="stable")
    def parent():
        pass

    @reg.subfeature("net.wifi", "scan", description="scan for networks")
    def scan():
        return "scanning"

    assert scan() == "scanning"
    rec = reg.get("net.wifi.scan")
    assert rec is not None
    assert rec.parent_id == "net.wifi"
    assert rec.category == "network"
    assert rec.owner == "net-team"
    assert rec.status == "stable"
    assert rec.description == "scan for networks"


def test_hydrate_from_catalog_does_not_overwrite_code():
    _, reg = _fresh()

    @reg.feature("dual", status="experimental", owner="alice")
    def dual_fn():
        pass

    catalog = {
        "features": [
            {"id": "dual", "name": "Dual", "status": "stable", "owner": "bob"},
            {"id": "yamlonly", "name": "YamlOnly", "status": "stable"},
        ]
    }
    added = reg.hydrate_from_catalog(catalog)
    assert added == 1  # only yamlonly added; dual is code-source so skipped

    code_rec = reg.get("dual")
    assert code_rec.source == "code"
    assert code_rec.owner == "alice"  # not overwritten

    yaml_rec = reg.get("yamlonly")
    assert yaml_rec.source == "yaml"


def test_reconcile_flags_drift():
    _, reg = _fresh()

    @reg.feature("only.code", status="stable")
    def f1():
        pass

    @reg.feature("agreed", status="experimental")
    def f2():
        pass

    @reg.feature("disagree", status="experimental")
    def f3():
        pass

    catalog = {
        "features": [
            {"id": "agreed", "status": "experimental"},
            {"id": "disagree", "status": "stable"},  # mismatch
            {"id": "only.yaml", "status": "stable"},
        ]
    }
    diff = reg.reconcile_with_yaml(catalog)
    assert "only.code" in diff["in_code_only"]
    assert "only.yaml" in diff["in_yaml_only"]
    assert any("disagree" in s for s in diff["status_mismatch"])
    assert "agreed" not in diff["in_code_only"]
    assert "agreed" not in diff["in_yaml_only"]


def test_decorator_never_raises_on_bad_metadata():
    _, reg = _fresh()

    # commands as a non-iterable bad type — should not raise.
    @reg.feature("bad.meta", commands="not-a-list")  # type: ignore[arg-type]
    def fn():
        return 1

    # Either it registers (best-effort) or it returns the undecorated function;
    # either way it must not crash and the function must work.
    assert fn() == 1


def test_all_records_returns_snapshot():
    _, reg = _fresh()

    @reg.feature("a")
    def _a():
        pass

    @reg.feature("b")
    def _b():
        pass

    ids = {r.id for r in reg.all_records()}
    assert {"a", "b"} <= ids
