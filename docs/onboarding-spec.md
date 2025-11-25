```markdown
# Onboarding Flow Specification

This document defines the interactive `neo-rx setup` command used to prepare a host for running the APRS iGate.

## Goals
- Verify hardware and software prerequisites without modifying system-level configuration.
- Collect operator identity and station metadata needed for APRS-IS access.
- Persist configuration to `~/.config/neo-rx/config.toml` while protecting sensitive data.
- Prime support services (Direwolf, logging directories) and provide clear success/failure feedback.
- Support reruns (`--reset`, `--non-interactive`) for headless or scripted environments.

## Preconditions
- Host has Python 3.11+ with project virtual environment activated.
   - `neo-rx` CLI installed (`pip install -e '.[dev]'`).
- `direwolf` installed via system package manager or manual build.

> NOTE (Oct 2025): Packaging caveats
>
> - `aprslib >=0.8` is not available on PyPI as of this date; the project uses a relaxed constraint (`aprslib >=0.7.2,<0.9`) in `pyproject.toml` to allow installs. If you require `>=0.8`, consider pinning to a VCS URL or waiting for an official release.
> - `types-keyring` does not appear on PyPI; rely on the runtime `keyring` package for secure storage rather than a non-existent typing package.

## High-Level Steps
1. **Environment Checks**
   - Detect active virtual environment (`sys.prefix` under project root) and warn if missing.
   - Locate `direwolf` executable in `PATH`; fail with remediation guidance if not found.
   - Confirm `python3` executable version and required runtime dependencies (numpy, pyrtlsdr, aprslib).

2. **USB Device Verification**
   - Attempt `rtl_test` (or direct `pyrtlsdr.RtlSdr`) probe to ensure NESDR Smart v5 is accessible.
   - Check for required udev permissions (read/write). If insufficient, output instructions and pause for retry.
   - Capture recommended defaults: tuner gain options, RTL crystal correction (ppm), sample rate capability.

3. **Direwolf Sanity Test**
   - Offer to launch Direwolf with a lightweight test configuration (loopback input) or verify existing instance.
   - Validate KISS TCP port (default `127.0.0.1:8001`) is reachable and responds to version query.

4. **Station Identity Collection**
   - Prompt for callsign-SSID (e.g., `CALLSIGN-10`), APRS-IS passcode, optional operator name.
   - Prompt for station location: latitude, longitude, altitude (meters), optional comment/beacon text.
   - Provide default APRS-IS server rotation (`noam.aprs2.net`) with option to override or specify fallback list.

5. **Configuration Persistence**
   - Store collected data in `~/.config/neo-rx/config.toml` with mode `0o600`.
   - Passcode handling:
     - Prefer local keyring (Secret Service) via `keyring` lib; fall back to base64-encoded storage with warning if keyring unavailable.
   - Include derived settings: detected tuner gain, sample rate, KISS host/port, timestamp of onboarding.
   - Render Direwolf config from `docs/templates/direwolf.conf` into `~/.config/neo-rx/direwolf.conf` when user opts in to managed setup.

6. **Telemetry & Logging Setup**
   - Ask user if they want local logs retained and whether anonymized metrics may be collected (default off).
   - Ensure `~/.local/share/neo-rx/logs` exists with rotation policy notes.
   - Display guidance for host-managed rotation (recommend a weekly `logrotate` rule retaining four archives, with `copytruncate` for manual shells or `postrotate systemctl --user restart ...` for systemd services).

7. **Validation Run**
   - Optionally perform end-to-end dry run using bundled sample IQ:
     - Replay IQ to Direwolf, capture KISS frames, attempt APRS-IS login (test server) in dry-run mode.
     - Report success/failure and store results in onboarding summary.

8. **Completion Summary**
   - Display summary table outlining:
     - SDR detected and gain/sample defaults
     - Direwolf connection status
     - APRS-IS server(s)
     - Config file path and sensitive data storage method
   - Provide next command suggestions (`neo-rx listen`, `neo-rx diagnostics`).

## CLI Options
- `neo-rx setup`: interactive wizard (default).
- `neo-rx setup --reset`: delete existing config (confirm first) and rerun wizard.
- `neo-rx setup --non-interactive --config /path/to/file`: accept pre-filled TOML, only validate hardware/software.
- `neo-rx setup --dry-run`: perform validation without writing config changes.

## User Prompts & Validation Rules
- Callsign must match regex `^[A-Z0-9]{1,6}-[0-9]{1,2}$`; offer uppercase normalization.
- Latitude/longitude validated numeric: lat ∈ [-90, 90], lon ∈ [-180, 180].
- APRS-IS passcode masked during input; confirm entry by retyping.
- Server list accepts comma-separated hostnames; verify DNS resolution.

## Error Handling Strategy
- Use clear, actionable error messages; no raw tracebacks during onboarding unless `--debug` set.
- Offer retry loops for recoverable steps (USB permissions, Direwolf connection).
- Abort only when critical prerequisites fail after retries.

## Artifacts
- `~/.config/neo-rx/config.toml`: primary config file.
- `~/.config/neo-rx/direwolf.conf`: rendered Direwolf configuration (optional, managed flow).
- Keyring entry (`neo-rx/callsign`): secure passcode storage when available.
- `~/.local/share/neo-rx/logs/setup.log`: onboarding transcript for diagnostics.

## Open Questions
- Should onboarding auto-generate a Direwolf config file tailored to device, or simply validate user-provided config?
- Do we prompt for secondary SDR devices now, or defer until multi-backend support is implemented?
- How should we handle headless deployments where interactive prompts are impossible (env vars vs. config file)?

```
