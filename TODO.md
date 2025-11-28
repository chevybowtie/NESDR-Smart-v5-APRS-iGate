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
- Data: `~/.local/share/neo-rx/instances/{instance_id}/{aprs,wspr}/…`.
- Logs: `~/.local/share/neo-rx/instances/{instance_id}/logs/{aprs,wspr}/app.log`.
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
- [x] Create branch `feature/multi-tool`.
- [x] Extract `neo_core` and update imports.
	- Core helpers (`diagnostics_helpers`, `term`, `timeutils`) migrated; CLI moved to `neo_core.cli`.
	- Config migrated from `neo_rx` to `neo_core`; `neo_rx.config` is now a shim.
	- Radio capture migrated to `neo_core.radio`; `neo_rx.radio.capture` is now a shim.
- [x] Create `neo_telemetry` and update references.
	- MQTT publisher and ondisk queue migrated; `neo_rx.telemetry` modules are shims.
	- Tests now monkeypatch via `neo_rx.telemetry.mqtt_publisher` and are supported.
- [x] Carve `neo_aprs` and per-mode setup/diagnostics.
	- Protocol stack moved to `neo_aprs.aprs` with shims.
	- APRS commands migrated: `listen`, `setup`, `diagnostics`.
	- Unified CLI routes `neo-rx aprs <verb>` through `neo_aprs`.
- [x] Carve `neo_wspr` and per-mode setup/diagnostics; package `wsprd`.
	- WSPR modules migrated under `neo_wspr.wspr` with shims.
	- Commands implemented: `worker`, `scan`, `calibrate`, `upload`, `diagnostics`.
	- `wsprd` binary packaged with `neo_wspr`.
- [x] Implement unified CLI subcommands in `neo_core.cli`.
	- APRS/WSPR subcommands implemented; flag parity maintained.
- [x] Update and validate tests.
	- All tests now pass: 228/228.
	- Legacy private-API tests updated with compatible shims (`_PromptSession`, `prompt_yes_no`).
- [x] Config layering and validation (`defaults.toml`, `aprs.toml`, `wspr.toml`).
	- Multi-file layering implemented with precedence defaults < mode < env < CLI.
- [x] Namespace data/log paths per mode/instance.
	- [x] Implement per-instance directories under XDG paths.
- [x] Add concurrency tests.
	- Verified simultaneous APRS/WSPR on different SDRs via `--device-id` and `--instance-id`.
- [ ] Update docs (README, onboarding, diagnostics, radio-layer, direwolf, wspr).
- [ ] Update CI/release scripts for multi-package synchronized release.

Usage Examples:
- APRS: `neo-rx aprs setup`; `neo-rx aprs listen --device-id 00000001 --instance-id aprs-1`.
- WSPR: `neo-rx wspr setup`; `neo-rx wspr worker --device-id 00000002 --instance-id wspr-20m`.
- Concurrent: run both with distinct `--device-id` and `--instance-id`.


