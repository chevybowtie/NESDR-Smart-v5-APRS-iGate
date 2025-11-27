"""Config loader/merger for neo-rx multi-tool suite.

Layering order (lowest to highest precedence):
1. defaults.toml (shared identity + common radio/runtime)
2. <mode>.toml (aprs.toml or wspr.toml)
3. Environment (NEORX_*)
4. CLI flags

This module will expose a typed Config object and helpers to resolve
per-mode config with shared defaults.
"""

# Placeholder: implementation will be migrated from neo_rx.config
