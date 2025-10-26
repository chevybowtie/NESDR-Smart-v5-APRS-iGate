# Sample Capture Guide

This guide explains how to record SDR samples for local testing and onboarding validation.

## Requirements
- NESDR Smart v5 connected and visible to `rtl_test`.
- `rtl-sdr` utilities installed (`rtl_sdr`, `rtl_fm`). On Debian/Ubuntu:

	```bash
	sudo apt update
	sudo apt install rtl-sdr
	```

- Optional: `sox` for converting demodulated audio into WAV format (`sudo apt install sox`).

## Capture Script
Use `scripts/capture_samples.sh` to gather both raw IQ and audio captures. The script creates an entry in `samples/capture_summary.txt` so we can track the parameters used for each run.

```bash
chmod +x scripts/capture_samples.sh  # one-time
./scripts/capture_samples.sh
```

### Environment Overrides
The script accepts environment variables to tweak behavior:

- `FREQUENCY_HZ` (default `144390000`)
- `IQ_SAMPLE_RATE` (default `250000` samples/sec)
- `AUDIO_SAMPLE_RATE` (default `22050` samples/sec)
- `GAIN` (default `35` dB)
- `DURATION` (default `120` seconds)
- `RTL_DEVICE_INDEX` (default `0`)
- `RTL_PPM` (default `0`)
- `OUTPUT_DIR` (default `samples`)

Example:

```bash
FREQUENCY_HZ=144390200 DURATION=300 OUTPUT_DIR=samples/2025-10-25 ./scripts/capture_samples.sh
```

## Output Artifacts
- `*.raw` — raw binary data (IQ or 16-bit PCM audio)
- `*.wav` — optional WAV converted audio when `sox` is installed
- `capture_summary.txt` — append-only log of capture metadata

> **Note:** Large IQ files are ignored by git via `.gitignore`. To share samples, use an external storage mechanism.

## Next Steps
After recording, use the IQ files to drive Direwolf during onboarding validation and integration tests. Document interesting captures (e.g., heavy traffic, weak signals) in this folder for future reference.
