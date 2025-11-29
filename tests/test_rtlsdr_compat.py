import importlib.util
import sys
import types
from collections.abc import MutableMapping
from typing import Any

import pytest

from neo_rx._compat import rtlsdr  # type: ignore[attr-defined]


def _reset_rtlsdr(sys_modules: MutableMapping[str, Any]) -> None:
    sys_modules.pop("rtlsdr", None)


def test_patch_source_without_pkg_resources_returns_input() -> None:
    source = "print('hello')\n"
    assert rtlsdr._patch_source(source) == source


def test_patch_source_appends_fallback_when_sentinel_missing() -> None:
    source = "import pkg_resources\nVALUE = 1\n"
    patched = rtlsdr._patch_source(source)
    assert "pkg_resources" not in patched
    assert "VALUE = 1" in patched
    assert "_importlib_metadata" in patched


def test_ensure_patched_rtlsdr_returns_when_spec_missing(monkeypatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    _reset_rtlsdr(sys.modules)
    rtlsdr.ensure_patched_rtlsdr()
    assert "rtlsdr" not in sys.modules


def test_ensure_patched_rtlsdr_returns_when_loader_missing(monkeypatch) -> None:
    spec = types.SimpleNamespace(loader=None, origin="fake", name="rtlsdr")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: spec)
    _reset_rtlsdr(sys.modules)
    rtlsdr.ensure_patched_rtlsdr()
    assert "rtlsdr" not in sys.modules


def test_ensure_patched_rtlsdr_returns_without_get_source(monkeypatch) -> None:
    loader = types.SimpleNamespace()
    spec = types.SimpleNamespace(loader=loader, origin="fake", name="rtlsdr")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: spec)
    _reset_rtlsdr(sys.modules)
    rtlsdr.ensure_patched_rtlsdr()
    assert "rtlsdr" not in sys.modules


def test_ensure_patched_rtlsdr_returns_when_source_missing(monkeypatch) -> None:
    class Loader:
        def get_source(self, name: str) -> None:
            return None

    spec = types.SimpleNamespace(loader=Loader(), origin="fake", name="rtlsdr")
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: spec)
    _reset_rtlsdr(sys.modules)
    rtlsdr.ensure_patched_rtlsdr()
    assert "rtlsdr" not in sys.modules


def test_ensure_patched_rtlsdr_failure_cleans_sys_modules(monkeypatch) -> None:
    class Loader:
        def get_source(self, name: str) -> str:
            return "raise RuntimeError('boom')\n"

    spec = types.SimpleNamespace(
        loader=Loader(), origin="fake", name="rtlsdr", submodule_search_locations=None
    )

    def fake_module_from_spec(_spec: object) -> types.ModuleType:
        return types.ModuleType("rtlsdr")

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: spec)
    monkeypatch.setattr(importlib.util, "module_from_spec", fake_module_from_spec)
    _reset_rtlsdr(sys.modules)

    with pytest.raises(RuntimeError):
        rtlsdr.ensure_patched_rtlsdr()

    assert "rtlsdr" not in sys.modules
