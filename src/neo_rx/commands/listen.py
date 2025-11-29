"""Backward compatibility shim for APRS listen command.

This module re-exports from neo_aprs.commands to maintain backward compatibility.
"""

from neo_aprs.commands.listen import run_listen

__all__ = ["run_listen"]
