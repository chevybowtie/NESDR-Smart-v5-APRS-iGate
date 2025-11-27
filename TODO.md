Features:
* explore reverse beacon network (https://reversebeacon.net/)
* explore ADS-B 



Multi-Tool Split Plan:
- Goal: Split monolith into `neo_core`, `neo_aprs`, `neo_wspr`, `neo_telemetry`. Keep unified `neo-rx` CLI with `aprs`/`wspr` subcommands. Install all tools by default; synchronized versions.
- Concurrency: Support running APRS and WSPR simultaneously on different SDRs via `--device-id` and `--instance-id`.

CLI:
- Commands:
	- `neo-rx aprs <setup|listen|diagnostics>`
	- `neo-rx wspr <setup|worker|scan|calibrate|upload|diagnostics>`
- Shared flags: `--device-id`, `--instance-id`, `--config`, `--data-dir`, `--log-level`, `--no-color`, `--json`.
- APRS flags: `--kiss-host`, `--kiss-port`.
- WSPR flags: `--band`, `--duration`, `--schedule`, `--samples`, `--input`.

Config Precedence:
- Files: `~/.config/neo-rx/defaults.toml`, `~/.config/neo-rx/aprs.toml`, `~/.config/neo-rx/wspr.toml`.
- Order: defaults < mode < env < CLI flags.
- Shared identity: `identity.callsign`, `identity.grid`, `identity.location.lat|lon|alt_m`.
- APRS keys: `aprs.kiss.host|port`, `aprs.aprsis.user|passcode`, `aprs.direwolf.conf_path`.
- WSPR keys: `wspr.bands[]`, `wspr.decoder.bin_path`, `wspr.uploader.enabled|api_url`.

Paths:
- Data: `~/.local/share/neo-rx/{aprs,wspr}/instances/{instance_id}/…`.
- Logs: `~/.local/share/neo-rx/logs/{aprs,wspr}/instances/{instance_id}/app.log`.
- WSPR runs: `~/.local/share/neo-rx/wspr/runs/{timestamp or instance_id}/`.
- Templates: `neo_core.templates/direwolf.conf`.

Module Mapping:
- To `neo_core`: `config.py`, `term.py`, `diagnostics_helpers.py`, `timeutils.py`, `_compat/*`, `radio/*`, `templates/direwolf.conf`.
- To `neo_aprs`: `aprs/*`, `commands/listen.py`, `commands/setup.py`, `commands/diagnostics.py`.
- To `neo_wspr`: `wspr/*`, `wspr/bin/wsprd`, `commands/wspr.py`, `commands/setup.py`, `commands/diagnostics.py`.
- To `neo_telemetry`: `telemetry/*` (publishers, MQTT buffer).

Packaging:
- Metapackage `neo-rx` depends on `neo_core`, `neo_aprs`, `neo_wspr`, `neo_telemetry` (install-all default).
- Synchronized versions across all packages.

Progress Checklist:
- [ ] Create branch `feature/multi-tool`.
- [x] Extract `neo_core` and update imports.
	- Core helpers (`diagnostics_helpers`, `term`, `timeutils`) migrated; CLI moved to `neo_core.cli`.
	- **Config migrated from neo_rx to neo_core**; neo_rx.config is now a shim re-exporting from neo_core.
	- **Radio capture module migrated to neo_core.radio**; neo_rx.radio.capture is now a shim.
- [x] Create `neo_telemetry` and update references.
	- **MQTT publisher and ondisk_queue migrated to neo_telemetry**; neo_rx.telemetry modules are now shims.
	- All dependency extractions complete; both APRS and WSPR use new packages directly.
- [x] Carve `neo_aprs` and per-mode setup/diagnostics.
	- Protocol stack moved to `neo_aprs.aprs` (AX.25, KISS, APRS-IS) with backward-compat shims.
	- **APRS command implementations migrated**: `listen` (638 lines), `setup` (488 lines), `diagnostics` (383 lines).
	- **Real implementations now in neo_aprs.commands**; neo_rx.commands are shims.
	- Unified CLI routes `neo-rx aprs <verb>` through neo_aprs implementations.
- [x] Carve `neo_wspr` and per-mode setup/diagnostics; package `wsprd`.
	- WSPR modules migrated to `neo_wspr.wspr` (capture, decoder, uploader, calibrate, diagnostics, scan, publisher) with backward-compat shims.
	- WSPR command wrappers implemented: `worker`, `scan`, `calibrate`, `upload`, `diagnostics` with real logic.
	- Unified CLI routes `neo-rx wspr <verb>` through new implementations; legacy handler removed.
	- `wsprd` binary packaged with `neo_wspr`.
- [x] Implement unified CLI subcommands in `neo_core.cli`.
	- APRS and WSPR subcommands fully implemented; all verbs route to new packages.
	- Flag parity maintained: APRS (--reset, --dry-run, --non-interactive, --verbose), WSPR (--band, --json, etc.).
- [ ] Config layering and validation (`defaults.toml`, `aprs.toml`, `wspr.toml`).
	- Config module migrated to neo_core; multi-file layering deferred to future iteration.
- [ ] Namespace data/log paths per mode/instance.
- [ ] Update tests by mode; add concurrency tests.
- [ ] Update docs (README, onboarding, diagnostics, radio-layer, direwolf, wspr).
- [ ] Update CI/release scripts for multi-package synchronized release.

Usage Examples:
- APRS: `neo-rx aprs setup`; `neo-rx aprs listen --device-id 00000001 --instance-id aprs-1`.
- WSPR: `neo-rx wspr setup`; `neo-rx wspr worker --device-id 00000002 --instance-id wspr-20m`.
- Concurrent: run both with distinct `--device-id` and `--instance-id`.


