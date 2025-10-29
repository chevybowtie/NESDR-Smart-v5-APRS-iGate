"""CLI command handlers."""

from .diagnostics import run_diagnostics
from .listen import run_listen
from .setup import run_setup
from . import setup_io  # re-export helper module for lint visibility

__all__ = ["run_setup", "run_listen", "run_diagnostics", "setup_io"]

