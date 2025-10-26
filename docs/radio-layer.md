# Radio Layer Design

Defines the abstraction used to communicate with SDR hardware and the initial NESDR Smart v5 implementation.

## Objectives
- Provide a narrow interface the rest of the application can depend on (open → configure → stream → close).
- Support pluggable backends with consistent settings/status structures.
- Surface meaningful errors and diagnostics for onboarding/CLI reporting.
- Keep the NESDR backend thin while leaving room for future devices (Airspy, HackRF, etc.).

## Abstractions
- `RadioSettings`: dataclass describing tuning parameters (frequency, sample rate, gain, ppm, buffer length).
- `RadioStatus`: dataclass summarising device state for diagnostics (current tuning, gain, serial).
- `RadioBackend`: abstract base class that standardises `open`, `configure`, `read_samples`, `get_status`, `close`.
- `RadioError`: raised for recoverable backend failures (missing drivers, IO issues, etc.).

## NESDR Backend
- Uses `pyrtlsdr` (`rtlsdr.RtlSdr`) for hardware access.
- Lazily opens the device on first use; supports explicit context manager usage.
- Applies settings with graceful fallbacks (`gain=None` disables manual gain, uses tuner auto mode).
- Returns IQ samples using `read_samples`, leaving post-processing (AGC, filtering) to upper layers.
- Provides helpful error messages when `pyrtlsdr` is missing or hardware access fails.

## Future Enhancements
- Expose asynchronous streaming helpers (callbacks/background threads) for continuous capture.
- Add calibration helpers (PPM estimation) and gain sweep utilities.
- Implement additional backends by conforming to the same interface.
- Cache device metadata (serial, manufacturer) during `open` for richer diagnostics.
