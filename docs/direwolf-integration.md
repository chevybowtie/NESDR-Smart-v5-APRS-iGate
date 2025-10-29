# Direwolf Integration Plan

This document outlines how the `neo-igate` CLI will interact with Direwolf for APRS packet decoding and uplink.

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
-- The template includes a KISS port definition, IGate beacon entry, and logging directory pointing to `~/.local/share/neo-igate/logs`.
-- Onboarding copies the template to `$XDG_CONFIG_HOME/neo-igate/direwolf.conf`, substituting operator-specific values.

## Audio Feed Strategy

## Health Checks

The following health checks are performed:
  - TCP connect to `KISS_HOST:KISS_PORT` and send `0xC0 0xFF 0xC0` (FEND FESC FEND) to validate response.
  - Optional Direwolf `--version` or status command for logging.
  - If running managed Direwolf, tail last log lines to ensure no fatal errors.
  - KISS socket connectivity and round-trip timing.
  - Recent packet counts from Direwolf log (if accessible).

## Error Handling

## Logging
- `scripts/run_direwolf.sh` appends Direwolf output to `~/.local/share/neo-igate/logs/direwolf.log`.
## Open Questions
- Should we standardize on ALSA loopback + managed Direwolf to simplify user setup?
