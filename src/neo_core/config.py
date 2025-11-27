"""Compatibility layer for configuration during refactor.

For the initial phase of the split, reuse the existing implementation
from ``neo_rx.config`` so new code can import ``neo_core.config``
without breaking tests. The implementation will be migrated here in a
subsequent step.
"""

from neo_rx.config import *  # noqa: F401,F403 re-export during migration
