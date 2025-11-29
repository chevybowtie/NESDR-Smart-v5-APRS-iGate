"""Neo-RX package.

Expose a single runtime version value (``__version__``) so modules
within the package can consistently report the package version at
runtime without duplicating fallback logic.
"""

# Suppress pkg_resources deprecation warning
import warnings

from pathlib import Path as _Path

try:
    # Python 3.8+ exposes importlib.metadata in the stdlib; fall back to
    # the backport package if necessary. We keep this minimal and avoid
    # importing package submodules before __version__ is set to prevent
    # circular import issues.
    from importlib import metadata as _importlib_metadata
except Exception:  # pragma: no cover - defensive for very old runtimes
    import importlib_metadata as _importlib_metadata  # type: ignore

warnings.filterwarnings(
    "ignore", message="pkg_resources is deprecated", category=UserWarning
)

_pkg_path = _Path(__file__).resolve()
_in_site = ("site-packages" in str(_pkg_path)) or ("dist-packages" in str(_pkg_path))


def _version_from_pyproject() -> str:
    try:
        import sys as _sys

        if _sys.version_info >= (3, 11):
            import tomllib as _toml
        else:  # pragma: no cover
            import tomli as _toml  # type: ignore
        _root = _pkg_path.parents[2]
        _pyproj = _root / "pyproject.toml"
        if _pyproj.exists():
            with _pyproj.open("rb") as _f:
                _data = _toml.load(_f)
            return _data.get("project", {}).get("version", "0.0.0")
    except Exception:
        pass
    return "0.0.0"


if not _in_site:
    __version__ = _version_from_pyproject()
else:
    try:
        __version__ = _importlib_metadata.version("neo-rx")
    except Exception:
        __version__ = _version_from_pyproject()

from . import cli, config, diagnostics_helpers, term  # noqa: E402

__all__ = ["cli", "config", "diagnostics_helpers", "term", "__version__"]
