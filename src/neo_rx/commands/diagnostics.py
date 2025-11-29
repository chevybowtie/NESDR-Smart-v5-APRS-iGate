"""Backward compatibility shim for APRS diagnostics command.

This module re-exports from neo_aprs.commands to maintain backward compatibility.
"""

from neo_aprs.commands.diagnostics import run_diagnostics

__all__ = ["run_diagnostics"]
