"""Compatibility shims for pyrtlsdr and related SDR libs.

Provides a best-effort `prepare_rtlsdr` that avoids importing heavy
dependencies during tests by injecting a lightweight stub module if
`rtlsdr` is unavailable.
"""

from __future__ import annotations

import types
import sys


def prepare_rtlsdr() -> None:
	"""Install a minimal stub for `rtlsdr` if import would fail.

	The stub exposes `RtlSdr.get_device_count()` and instance methods
	`set_ppm_offset()` and `close()` sufficient for calibration/tests.
	"""
	# If rtlsdr already importable, do nothing
	try:
		__import__("rtlsdr")
		return
	except Exception:
		pass

	# Provide a minimal stub to satisfy code paths in tests
	mod = types.ModuleType("rtlsdr")

	class _RtlSdr:
		@staticmethod
		def get_device_count() -> int:
			# Default to one device present for positive-path tests; tests
			# can override by monkeypatching if needed
			return 1

		def set_ppm_offset(self, _ppm: int) -> None:  # noqa: D401
			return None

		def close(self) -> None:
			return None

	setattr(mod, "RtlSdr", _RtlSdr)
	sys.modules["rtlsdr"] = mod
