"""Configuration layering support for multi-file precedence.

Supports loading and merging multiple TOML configuration files with
precedence: defaults.toml < mode-specific.toml < environment variables < CLI args.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    import tomli as tomllib  # type: ignore[no-redef]


def load_layered_config(
    mode: str | None = None,
    config_dir: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and merge configuration from multiple sources.

    Precedence (later overrides earlier):
    1. defaults.toml (if present)
    2. <mode>.toml (e.g., aprs.toml or wspr.toml, if mode is specified)
    3. Environment variables (NEO_RX_* prefix)
    4. CLI overrides (passed as dict)

    Args:
        mode: Optional mode name ("aprs" or "wspr") to load mode-specific config.
        config_dir: Directory containing config files; defaults to get_config_dir().
        cli_overrides: Dictionary of CLI-provided overrides (flat or nested).

    Returns:
        Merged configuration dictionary.
    """
    if config_dir is None:
        from neo_core.config import get_config_dir

        config_dir = get_config_dir()

    # Start with defaults
    result: dict[str, Any] = {}
    defaults_path = config_dir / "defaults.toml"
    if defaults_path.exists():
        result = _load_toml_file(defaults_path)

    # Merge mode-specific config
    if mode:
        mode_path = config_dir / f"{mode}.toml"
        if mode_path.exists():
            mode_data = _load_toml_file(mode_path)
            result = _deep_merge(result, mode_data)

    # Apply environment variable overrides
    env_overrides = _extract_env_overrides()
    if env_overrides:
        result = _deep_merge(result, env_overrides)

    # Apply CLI overrides
    if cli_overrides:
        result = _deep_merge(result, cli_overrides)

    return result


def _load_toml_file(path: Path) -> dict[str, Any]:
    """Load a TOML file and return its contents as a dictionary."""
    with path.open("rb") as handle:
        return tomllib.load(handle)  # type: ignore[no-any-return]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, preferring override values.

    For nested dicts, merge recursively. For all other types, override replaces base.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _extract_env_overrides() -> dict[str, Any]:
    """Extract NEO_RX_* environment variables into a nested config dict.

    Env var naming convention:
    - NEO_RX_SECTION__KEY → {"section": {"key": value}}
    - NEO_RX_KEY → {"key": value}

    Example:
        NEO_RX_APRS__SERVER=localhost → {"aprs": {"server": "localhost"}}
    """
    overrides: dict[str, Any] = {}
    prefix = "NEO_RX_"

    for env_key, env_value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        suffix = env_key[len(prefix) :]
        if not suffix:
            continue

        # Split on double underscore for section nesting
        parts = suffix.lower().split("__")
        if len(parts) == 1:
            # Top-level key
            overrides[parts[0]] = _parse_env_value(env_value)
        elif len(parts) == 2:
            # Nested key: section.key
            section, key = parts
            if section not in overrides:
                overrides[section] = {}
            if isinstance(overrides[section], dict):
                overrides[section][key] = _parse_env_value(env_value)

    return overrides


def _parse_env_value(raw: str) -> Any:
    """Parse environment variable string into appropriate Python type.

    - "true"/"false" → bool
    - Numeric strings → int or float
    - Everything else → str
    """
    lower = raw.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    # Try int
    try:
        return int(raw)
    except ValueError:
        pass
    # Try float
    try:
        return float(raw)
    except ValueError:
        pass
    return raw
