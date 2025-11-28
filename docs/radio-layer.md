# Radio Layer Design

Defines the abstraction used to communicate with SDR hardware and the RTL-SDR implementation.

## Objectives
- Provide a narrow interface the rest of the application can depend on (open → configure → stream → close).
- Support pluggable backends with consistent settings/status structures.
- Support concurrent operation via device selection (`--device-id`).
- Surface meaningful errors and diagnostics for onboarding/CLI reporting.
- Keep the RTL-SDR backend thin while leaving room for future devices (Airspy, HackRF, etc.).

## Abstractions
- `RadioSettings`: dataclass describing tuning parameters (frequency, sample rate, gain, ppm, buffer length).
- `RadioStatus`: dataclass summarising device state for diagnostics (current tuning, gain, serial).
- `RadioBackend`: abstract base class that standardises `open`, `configure`, `read_samples`, `get_status`, `close`.
- `RadioError`: raised for recoverable backend failures (missing drivers, IO issues, etc.).

## RTL-SDR Backend
- Uses `pyrtlsdr` (`rtlsdr.RtlSdr`) for hardware access via `neo_core.radio` module.
- Lazily opens the device on first use; supports explicit context manager usage.
- Device selection:
  - Enumeration via `get_device_count()`.
  - Selection by index (default 0) or serial number via `--device-id`.
- Applies settings with graceful fallbacks (`gain=None` disables manual gain, uses tuner auto mode).
- Returns IQ samples using `read_samples`, leaving post-processing (AGC, filtering) to upper layers.
- Provides helpful error messages when `pyrtlsdr` is missing or hardware access fails.

## Concurrent Operation
- Multiple instances can access different RTL-SDR devices simultaneously:
  - Each command uses `--device-id SERIAL` to select a specific device.
  - Combined with `--instance-id NAME` for isolated data/log directories.
- Example:
  ```bash
  # Terminal 1: APRS on device 00000001
  neo-rx aprs listen --device-id 00000001 --instance-id aprs-east
  
  # Terminal 2: WSPR on device 00000002
  neo-rx wspr worker --device-id 00000002 --instance-id wspr-20m
  ```

## Future Enhancements
- Expose asynchronous streaming helpers (callbacks/background threads) for continuous capture.
- Add calibration helpers (PPM estimation via WSPR `neo-rx wspr calibrate`) and gain sweep utilities.
- Implement additional backends by conforming to the same interface.
- Cache device metadata (serial, manufacturer) during `open` for richer diagnostics.
