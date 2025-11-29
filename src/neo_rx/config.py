"""Backward compatibility shim for configuration.

This module re-exports the configuration implementation from neo_core.config
to maintain backward compatibility during the multi-package migration.
"""

from neo_core.config import (
    StationConfig,
    load_config,
    save_config,
    resolve_config_path,
    get_config_dir,
    get_data_dir,
    get_mode_data_dir,
    get_logs_dir,
    get_wspr_runs_dir,
    config_summary,
    keyring_supported,
    store_passcode_in_keyring,
    delete_passcode_from_keyring,
    CONFIG_VERSION,
    CONFIG_ENV_VAR,
    CONFIG_DIR_NAME,
    CONFIG_FILENAME,
    KEYRING_SERVICE,
    KEYRING_SENTINEL,
)

__all__ = [
    "StationConfig",
    "load_config",
    "save_config",
    "resolve_config_path",
    "get_config_dir",
    "get_data_dir",
    "get_mode_data_dir",
    "get_logs_dir",
    "get_wspr_runs_dir",
    "config_summary",
    "keyring_supported",
    "store_passcode_in_keyring",
    "delete_passcode_from_keyring",
    "CONFIG_VERSION",
    "CONFIG_ENV_VAR",
    "CONFIG_DIR_NAME",
    "CONFIG_FILENAME",
    "KEYRING_SERVICE",
    "KEYRING_SENTINEL",
]
