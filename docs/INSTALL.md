# Installation (Debian 13)

This document describes the interactive `install.sh` installer and manual
steps for installing Neo-RX on Debian 13.

Quick: run the installer (interactive):

```bash
https://raw.githubusercontent.com/chevybowtie/NESDR-Smart-v5-APRS-iGate/refs/heads/develop/install.sh | bash
```

Common options:

- `--dry-run` — show actions without making changes.
- `--yes` — assume yes to prompts (non-interactive).
- `--target-dir PATH` — where to create the virtualenv and install files (default: `~/.local/share/neo-rx`).

The installer downloads a tarball (master branch archive) and installs in a
virtualenv. By default it will prompt for system package installation (it
will not enable or create services automatically).

The installer will first attempt to download the CI-published release asset
at:

```
https://github.com/chevybowtie/NESDR-Smart-v5-APRS-iGate/releases/download/master-latest/repo-master.tar.gz
```

If that asset is not yet available the installer falls back to the default
branch archive at:

```
https://github.com/chevybowtie/NESDR-Smart-v5-APRS-iGate/archive/refs/heads/master.tar.gz
```

No additional environment variables are required; the installer uses the
release asset URL first and the branch archive as a fallback.

Suggested apt packages (manual install):

```bash
sudo apt update
sudo apt install -y python3 python3-venv curl tar
```

Optional packages for SDR/APRS features:

```bash
sudo apt install -y rtl-sdr direwolf sox
```

After running the installer, render and review the Direwolf configuration:

```bash
~/.local/share/neo-rx/.venv/bin/neo-rx aprs setup
```

To run Direwolf with the bundled helper script once `~/.config/neo-rx/direwolf.conf`
is created, use:

```bash
./scripts/run_direwolf.sh
```

Systemd unit (sample — installer does NOT create this automatically):

```ini
[Unit]
Description=Neo-RX Direwolf helper

[Service]
ExecStart=%h/.local/share/neo-rx/.venv/bin/neo-rx aprs listen
Restart=on-failure

[Install]
WantedBy=default.target
```

If you prefer to manage a system service, create a `systemd --user` unit and enable it manually.

If you want the installer to automatically fetch a master archive from GitHub
when pushes to `master` occur, create a GitHub Actions job that produces a
branch archive URL — a placeholder workflow file is included in the repo as
`.github/workflows/generate-archive.yml` (implement CI later).
