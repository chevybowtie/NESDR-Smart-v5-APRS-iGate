"""Helpers to load ``rtlsdr`` without the ``pkg_resources`` warning.

The upstream ``pyrtlsdr`` package still imports ``pkg_resources`` at module
import time purely to determine its own version. Importing ``pkg_resources``
now emits a deprecation warning, so we pre-load the module with a patched
version that uses ``importlib.metadata`` instead.
"""

from __future__ import annotations

import importlib.util
import sys
from typing import Callable


def _patch_source(source: str) -> str:
    """Drop the ``pkg_resources`` import and use importlib.metadata instead."""
    if "pkg_resources" not in source:
        return source

    updated = source.replace("import pkg_resources\n", "")

    sentinel = (
        "try:\n"
        "    __version__ = pkg_resources.require('pyrtlsdr')[0].version\n"
        "except: # pragma: no cover\n"
        "    __version__ = 'unknown'\n"
    )

    replacement = (
        "try:\n"
        "    from importlib import metadata as _importlib_metadata\n"
        "except ImportError:  # pragma: no cover\n"
        "    import importlib_metadata as _importlib_metadata\n\n"
        "try:\n"
        "    __version__ = _importlib_metadata.version('pyrtlsdr')\n"
        "except _importlib_metadata.PackageNotFoundError:  # pragma: no cover\n"
        "    __version__ = 'unknown'\n"
    )

    if sentinel in updated:
        return updated.replace(sentinel, replacement)

    # Fall back to appending replacement logic for future source variants.
    return updated + "\n" + replacement


def ensure_patched_rtlsdr() -> None:
    """Load ``rtlsdr`` with a patched version block if possible."""
    if "rtlsdr" in sys.modules:
        return

    spec = importlib.util.find_spec("rtlsdr")
    if spec is None or spec.loader is None or spec.origin is None:
        return

    get_source: Callable[[str], str | None] | None = getattr(spec.loader, "get_source", None)
    if get_source is None:
        return

    source = get_source("rtlsdr")
    if source is None:
        return

    patched_source = _patch_source(source)

    module = importlib.util.module_from_spec(spec)
    module_dict = module.__dict__
    module_dict.setdefault("__file__", spec.origin)
    module_dict.setdefault("__loader__", spec.loader)
    module_dict.setdefault("__package__", spec.name)
    module_dict.setdefault("__spec__", spec)
    if spec.submodule_search_locations is not None:
        module_dict.setdefault("__path__", list(spec.submodule_search_locations))

    sys.modules[spec.name] = module
    try:
        exec(compile(patched_source, spec.origin, "exec"), module_dict)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise