## RTL-SDR Thermal Issues

**Symptoms**: RTL-SDR device disappears after sustained operation, runs hot, or causes readsb/decoder to crash.

**Root Cause**: Auto-gain setting (`--gain auto`) causes RTL-SDR RF amplifier to operate at maximum power, generating excessive heat that can trigger thermal shutdown.

**Solution**:
1. Use fixed gain instead of auto-gain (e.g., `--gain 35` instead of `--gain auto`)
   - This reduces RF amplifier power by ~50-60%
   - Typical stable gains range from 20-48 dB depending on your location
2. Use serial number device addressing instead of USB index
   - ❌ Fragile: `--device 0` (breaks after USB re-enumeration)
   - ✅ Robust: `--device=67411606` (based on physical hardware ID)
3. Discover your device's serial: `neo-rx adsb find-devices`

**Configuration Update Example** (for readsb in `/etc/default/readsb`):
```bash
# Before (thermal issues)
RECEIVER_OPTIONS="--device 0 --device-type rtlsdr --gain auto --ppm 0"

# After (stable)
RECEIVER_OPTIONS="--device=67411606 --device-type rtlsdr --gain 35 --ppm 0"
```

**Verification**:
- Run `neo-rx adsb diagnostics --verbose` to confirm config validation passes
- Watch for: `device_addressing: serial_number (robust)` and `gain_setting: 35`

---

## General Troubleshooting Tips
- Verify the dongle is hearing RF by piping audio to PulseAudio speakers:
	`rtl_fm -f 146520000 -M fm -s 22050 -g 35 -E deemp -A fast -F 9 | paplay --raw --rate=22050 --channels=1 --format=s16le --`
	Replace `146520000` with the frequency carrying the APRS audio, and adjust
	gain (`-g`) or center frequency slightly if the tones sound weak.
- Use `rtl_test -p` to measure your dongle's PPM error and update the config (`ppm_correction`) so rtl_fm and the CLI stay on frequency.
- If the CLI isn't decoding your handheld, double-check that the handheld is
  transmitting on the frequency being monitored; small offsets are enough to
  confuse Direwolf.
- Use `neo-rx {mode} find-devices` to discover RTL-SDR serial numbers before configuration, ensuring robust device addressing.
