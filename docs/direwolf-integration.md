# Direwolf Integration Plan

This document outlines how the `nesdr-igate` CLI will interact with Direwolf for APRS packet decoding and uplink.

## Goals
- Launch or connect to a Direwolf instance configured for the NESDR audio feed.
- Maintain a reliable KISS TCP connection for packet ingress/egress.
- Validate Direwolf health during onboarding and runtime.
- Keep configuration simple for operators familiar with Direwolf while providing sane defaults.

## Deployment Options
1. **External Direwolf Process (default)**
   - Operator runs Direwolf independently with supplied config file.
   - CLI verifies connectivity to `127.0.0.1:8001` before starting SDR capture.
2. **Managed Direwolf (future enhancement)**
   - CLI spawns Direwolf as a subprocess using a generated config.
   - Requires process supervision, log handling, and graceful shutdown.

## Configuration Template
- Template located at `docs/templates/direwolf.conf`.
- Placeholders (`{{CALLSIGN}}`, `{{PASSCODE}}`, etc.) will be populated during onboarding or by a separate rendering step.
- Defaults assume audio delivered via stdin (`ADEVICE stdin null`) using a 22.05 kHz mono stream from `rtl_fm`.
- The template includes a KISS port definition, IGate beacon entry, and logging directory pointing to `~/.local/share/nesdr-igate/logs`.
- Onboarding copies the template to `$XDG_CONFIG_HOME/nesdr-igate/direwolf.conf`, substituting operator-specific values.

## Audio Feed Strategy
- **Current implementation**: `scripts/run_direwolf.sh` pipes `rtl_fm` output directly into `direwolf -` with matching sample rate.
- Script handles rtl_fm/Direwolf availability checks, logging, and environment overrides (gain, frequency, ppm, config path).
- Advanced setups (ALSA loopback, external audio devices) can adjust `ADEVICE` in the rendered config and bypass the helper script.

## Health Checks
- **Setup command** performs:
  - TCP connect to `KISS_HOST:KISS_PORT` and send `0xC0 0xFF 0xC0` (FEND FESC FEND) to validate response.
  - Optional Direwolf `--version` or status command for logging.
  - If running managed Direwolf, tail last log lines to ensure no fatal errors.
- **Diagnostics command** shows:
  - KISS socket connectivity and round-trip timing.
  - Recent packet counts from Direwolf log (if accessible).

## Error Handling
- If KISS connection fails, surface actionable message: remind user to start Direwolf or adjust host/port.
- On unexpected disconnect, attempt limited retries; if unsuccessful, stop SDR capture and exit with non-zero status.
- Provide `--retry-kiss` flag to tune retry attempts/interval.

## Logging
- `scripts/run_direwolf.sh` appends Direwolf output to `~/.local/share/nesdr-igate/logs/direwolf.log`.
- External setups should enable `LOGDIR`/`LOGFILE` within their config to allow diagnostics to surface recent events.

## Open Questions
- Should we standardize on ALSA loopback + managed Direwolf to simplify user setup?
- Do we need to support Direwolf running on a remote host (KISS over LAN)?
- How do we expose Direwolf config tweaks (e.g., modem settings) without overwhelming the CLI interface?
