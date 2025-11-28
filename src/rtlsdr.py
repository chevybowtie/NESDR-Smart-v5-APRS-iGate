"""Local lightweight stub for rtlsdr to support tests.

Provides a minimal `RtlSdr` class so tests can patch methods without
pulling in external dependencies.
"""

class RtlSdr:
    @staticmethod
    def get_device_count() -> int:
        return 1

    def set_ppm_offset(self, _ppm: int) -> None:
        return None

    def close(self) -> None:
        return None
