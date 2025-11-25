# Direwolf Installation and Setup (Debian)

These steps install Direwolf on a Debian-based system (tested on Debian 12 "Bookworm") and prepare it for use with the `neo-rx` CLI.

## 1. Install Packages

```
sudo apt update
sudo apt install direwolf rtl-sdr sox
```

Optional utilities:

- `direwolf-doc` for manpages and examples
- `alsa-utils` if you plan to route audio through ALSA instead of stdin

## 2. Verify Installation

```
direwolf -v
```

You should see the Direwolf version and build information. If the command is not found, confirm that `/usr/bin` is in your `PATH` and that the `direwolf` package installed successfully.

## 3. Prepare Config Directory

```
mkdir -p ~/.config/neo-rx
mkdir -p ~/.local/share/neo-rx/logs
```

The CLI expects the Direwolf configuration at `~/.config/neo-rx/direwolf.conf` by default and stores logs under `~/.local/share/neo-rx/logs`.

## 4. Render Direwolf Configuration

Either run the CLI onboarding (which can render the file automatically) or copy the template manually:

```
cp docs/templates/direwolf.conf ~/.config/neo-rx/direwolf.conf
```

When `neo-rx setup` completes, accept the prompt to create `direwolf.conf` and the wizard will prefill your callsign, APRS-IS server, passcode, and KISS port values. Manually run the copy above if you prefer to edit the template yourself.

Edit the file to confirm your callsign, passcode, latitude/longitude, and beacon text. Leave `ADEVICE stdin null` if you intend to use `rtl_fm` piping via `scripts/run_direwolf.sh`.

Key fields to update:

- `MYCALL` – your APRS callsign with SSID (e.g., `KJ5EVH-10`)
- `IGLOGIN` – `CALLSIGN PASSCODE` pair for APRS-IS uplink
- `IGSERVER` – choose a tier 2 server close to you (e.g., `noam.aprs2.net 14580`)
- `PBEACON` – adjust comment text to describe your station
- `KISSPORT 8001` – leave as-is unless you plan to change the port for the CLI

## 5. Run Direwolf with NESDR Audio

Use the helper script to start the SDR capture and feed Direwolf:

```
./scripts/run_direwolf.sh
```

The script checks for `rtl_fm` and `direwolf`, configures gain and frequency defaults for 144.39 MHz, and writes logs to `~/.local/share/neo-rx/logs/direwolf.log`.

Common environment overrides:

```
NEO_RX_GAIN=35 NEO_RX_FREQ=144.39M ./scripts/run_direwolf.sh
```

If you prefer manual control, mimic the helper script:

```
rtl_fm -f 144.39M -s 22.05k -g 35 -p 0 - | direwolf -c ~/.config/neo-rx/direwolf.conf -
```

## 6. Enable KISS Port Access

Confirm that your config includes a KISS port listener:

```
KISSPORT 8001
```

After Direwolf starts, you should see a log line similar to:

```
KISS TCP port 8001 bound to 127.0.0.1
```

The `neo-rx diagnostics` command will probe `127.0.0.1:8001`; adjust the CLI config if you use a different address or port.

## 7. Test with Diagnostics

With Direwolf running you can validate the setup using the CLI.

```
neo-rx diagnostics
```

Expected output snippet:

```
[OK     ] Direwolf: KISS endpoint reachable at 127.0.0.1:8001
```

If you see a warning instead, ensure Direwolf is running, the KISS port matches your CLI configuration, and that no firewall rules block localhost connections.

## 8. Optional: Autostart Service

To launch Direwolf at boot, create a systemd user unit:

```
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/nesdr-direwolf.service <<'EOF'
[Unit]
Description=NESDR Direwolf gateway
After=network-online.target

[Service]
ExecStart=%h/Documents/projects/nesdr-aprs-igate/scripts/run_direwolf.sh
Restart=on-failure

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now nesdr-direwolf.service
```

Log files still land in `~/.local/share/neo-rx/logs/`. Add a host-level `logrotate` rule (weekly, `rotate 4`, `compress`) targeting `~/.local/share/neo-rx/logs/*.log` so Direwolf and CLI logs expire after four weeks. When running under systemd you have two options:

- Keep `copytruncate` in the `logrotate` stanza so Direwolf keeps writing uninterrupted.
- Or omit `copytruncate` and add a `postrotate systemctl --user restart nesdr-direwolf.service` block so the service reopens a fresh file when rotation occurs.

Check status with `systemctl --user status nesdr-direwolf.service`. Disable with `systemctl --user disable --now nesdr-direwolf.service`.

---

Direwolf should now accept KISS TCP connections from the CLI and forward decoded packets to APRS-IS using your credentials. Use `tail -f ~/.local/share/neo-rx/logs/direwolf.log` or `direwolf -t 0` output to monitor packet activity.
