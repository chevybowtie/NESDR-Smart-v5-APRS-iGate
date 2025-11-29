"""Backward compatibility shim for APRS setup command.

This module re-exports from neo_aprs.commands to maintain backward compatibility.
"""

from neo_aprs.commands.setup import run_setup

__all__ = ["run_setup"]
