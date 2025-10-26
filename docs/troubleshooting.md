## Troubleshooting Tips
- Verify the dongle is hearing RF by piping audio to PulseAudio speakers:
	`rtl_fm -f 144390000 -M fm -s 22050 -g 35 -E deemp -A fast -F 9 | paplay --raw --rate=22050 --channels=1 --format=s16le --`
	Adjust gain (`-g`) or center frequency slightly if APRS tones sound weak.
- Use `rtl_test -p` to measure your dongle's PPM error and update the config (`ppm_correction`) so rtl_fm and the CLI stay on frequency.
- If the CLI isn't decoding your handheld, double-check the handheld is transmitting right on 144.390 MHz; small offsets are enough to confuse Direwolf.
