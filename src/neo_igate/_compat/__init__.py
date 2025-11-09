"""Compatibility shims for third-party dependencies."""

from __future__ import annotations

import importlib

def prepare_rtlsdr() -> None:
    """Ensure the ``rtlsdr`` module loads without deprecated APIs."""

    try:
        compat_module = importlib.import_module("neo_igate._compat.rtlsdr")
    except ModuleNotFoundError:  # pragma: no cover - shim missing only in broken envs
        return

    patch_func = getattr(compat_module, "ensure_patched_rtlsdr", None)
    if callable(patch_func):
        patch_func()
