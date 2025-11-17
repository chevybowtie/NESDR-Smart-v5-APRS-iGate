"""Neo-RX package.

Expose a single runtime version value (``__version__``) so modules
within the package can consistently report the package version at
runtime without duplicating fallback logic.
"""

try:
    # Python 3.8+ exposes importlib.metadata in the stdlib; fall back to
    # the backport package if necessary. We keep this minimal and avoid
    # importing package submodules before __version__ is set to prevent
    # circular import issues.
    from importlib import metadata as _importlib_metadata
except Exception:  # pragma: no cover - defensive for very old runtimes
    import importlib_metadata as _importlib_metadata  # type: ignore

try:
    __version__ = _importlib_metadata.version("neo-rx")
except Exception:
    # When running from source (not installed) metadata may be absent;
    # fall back to a sensible dev placeholder.
    __version__ = "0.0.0"

# Suppress pkg_resources deprecation warning
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)

from . import cli, config, diagnostics_helpers, term

__all__ = ["cli", "config", "diagnostics_helpers", "term", "__version__"]
