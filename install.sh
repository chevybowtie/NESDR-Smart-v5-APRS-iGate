#!/usr/bin/env bash
set -euo pipefail

# If the script was invoked with `sh` (dash) rather than `bash`, re-exec
# with the user's `bash` so bash-specific features (like $'...' escapes)
# and color handling work reliably.
if [ -z "${BASH_VERSION:-}" ]; then
  if command -v bash >/dev/null 2>&1; then
    exec bash "$0" "$@"
  else
    echo "Warning: bash not found; continuing with /bin/sh may disable colors and some features." >&2
  fi
fi

# Neo-RX installer (Debian 13-targeted, interactive)
# - Downloads the repository master archive (no git required)
# - Creates a virtualenv, installs the package editable with selected extras
# - Prompts before running `sudo apt` installs (supports --dry-run and --yes)

PROG_NAME=$(basename "$0")
DRY_RUN=0
ASSUME_YES=0
TARGET_DIR=${TARGET_DIR:-$HOME/.local/share/neo-rx}
BRANCH_ARCHIVE_URL=https://github.com/chevybowtie/NESDR-Smart-v5-APRS-iGate/archive/refs/heads/master.tar.gz
# Release asset published by the workflow: stable filename and URL
RELEASE_ASSET_URL=https://github.com/chevybowtie/NESDR-Smart-v5-APRS-iGate/releases/download/master-latest/repo-master.tar.gz

usage() {
  cat <<EOF
Usage: $PROG_NAME [--dry-run] [--yes] [--target-dir PATH]

Options:
  --dry-run      Show steps but don't execute network or package changes.
  --yes          Assume yes to prompts (non-interactive).
  --target-dir   Directory to install into (default: $TARGET_DIR)

Notes:
  - The installer will attempt to download the release asset published by
    CI and fall back to the default branch archive if the asset is unavailable.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    --target-dir) TARGET_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

run_or_echo() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "DRY RUN: $*"
  else
    echo "+ $*"
    eval "$@"
  fi
}

# Color support: enable when stdout is a tty, TERM isn't 'dumb', and NO_COLOR not set.
# Prefer `tput` if available; otherwise fall back to basic ANSI escape sequences.
if [ -t 1 ] && [ "${TERM:-}" != "dumb" ] && [ "${NO_COLOR:-}" != "1" ]; then
  if command -v tput >/dev/null 2>&1; then
    ncolors=$(tput colors 2>/dev/null || 0)
  else
    # assume basic color support when tput is unavailable but we're a tty
    ncolors=8
  fi
else
  ncolors=0
fi

if [ "$ncolors" -ge 8 ]; then
  if command -v tput >/dev/null 2>&1; then
    COLOR_RESET=$(tput sgr0)
    COLOR_RED=$(tput setaf 1)
    COLOR_GREEN=$(tput setaf 2)
    COLOR_YELLOW=$(tput setaf 3)
    COLOR_BLUE=$(tput setaf 4)
    COLOR_CYAN=$(tput setaf 6)
  else
    COLOR_RESET=$'\033[0m'
    COLOR_RED=$'\033[0;31m'
    COLOR_GREEN=$'\033[0;32m'
    COLOR_YELLOW=$'\033[0;33m'
    COLOR_BLUE=$'\033[0;34m'
    COLOR_CYAN=$'\033[0;36m'
  fi
else
  COLOR_RESET=""
  COLOR_RED=""
  COLOR_GREEN=""
  COLOR_YELLOW=""
  COLOR_BLUE=""
  COLOR_CYAN=""
fi

info() { printf "%s%s%s\n" "$COLOR_CYAN" "$*" "$COLOR_RESET"; }
succ() { printf "%s%s%s\n" "$COLOR_GREEN" "$*" "$COLOR_RESET"; }
warn() { printf "%s%s%s\n" "$COLOR_YELLOW" "$*" "$COLOR_RESET"; }
err() { printf "%s%s%s\n" "$COLOR_RED" "$*" "$COLOR_RESET" >&2; }

# Override run_or_echo printing to be colored when supported
run_or_echo() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf "%sDRY RUN:%s %s\n" "$COLOR_YELLOW" "$COLOR_RESET" "$*"
  else
    printf "%s+%s %s\n" "$COLOR_GREEN" "$COLOR_RESET" "$*"
    eval "$@"
  fi
}

# Ensure python3 and venv helper exist (but do not apt-install automatically)
info "Installer target directory: $TARGET_DIR"

info "Attempting release asset first, then falling back to branch archive if needed."

apt_suggest="python3 python3-venv curl tar"
optional_pkgs="rtl-sdr direwolf sox"

# Prompt for extras early so we can install optional system packages when
# the user requests related features (e.g. Direwolf audio helpers).
chosen_extras=""
prompt_extra() {
  name=$1
  if [ "$ASSUME_YES" -eq 1 ]; then
    choice=Y
  else
    printf "Enable extra '%s'? [Y/n]: " "$name"
    IFS= read -r choice || true
    choice=${choice:-Y}
  fi
  case "$choice" in
    [Yy]*)
      if [ -z "$chosen_extras" ]; then
        chosen_extras="$name"
      else
        chosen_extras="$chosen_extras,$name"
      fi
      ;;
    *) ;;
  esac
}

prompt_extra aprs
prompt_extra wspr
prompt_extra direwolf

info "The system packages suggested for Debian 13 are: $apt_suggest"
info "Optional packages for SDR/APRS use: $optional_pkgs"
echo

if [ "$ASSUME_YES" -ne 1 ]; then
  printf "Run suggested apt installs now? (requires sudo) [y/N]: "
  IFS= read -r yn || true
  yn=${yn:-N}
else
  yn=Y
fi

echo

case "$yn" in
  [Yy]*)
    # Before attempting sudo, verify sudo exists and user has rights
    if command -v sudo >/dev/null 2>&1; then
      # Check whether current user is in the sudo group
      in_sudo_group=0
      if id -nG "$USER" 2>/dev/null | grep -qw sudo; then
        in_sudo_group=1
      fi

      if [ "$in_sudo_group" -eq 0 ]; then
        warn "Note: your user '$USER' is not in the 'sudo' group. To gain sudo rights run as root: 'usermod -aG sudo $USER' and then re-login."
        if [ "$ASSUME_YES" -eq 1 ]; then
          echo "Attempting to add $USER to sudo group using sudo..."
          run_or_echo "sudo usermod -aG sudo $USER" || true
          echo "You may need to log out and log back in for group changes to take effect."
        fi
      fi

      cmd="sudo apt update && sudo apt install -y $apt_suggest"
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "DRY RUN: $cmd"
      else
        info "Running: $cmd"
        bash -c "$cmd"
      fi

      # If the user enabled the 'direwolf' extra, install optional radio/audio packages
      case ",$chosen_extras," in
        *,direwolf,*)
          opt_cmd="sudo apt install -y $optional_pkgs"
          if [ "$DRY_RUN" -eq 1 ]; then
            echo "DRY RUN: $opt_cmd"
          else
            info "Installing optional packages for Direwolf: $optional_pkgs"
            bash -c "$opt_cmd"
          fi
          ;;
        *) ;;
      esac
    else
      echo
      warn "'sudo' not found on this system. The installer cannot run apt commands automatically."
      echo "To install the suggested packages as root, run as root or use 'su -c':"
      echo "  su -c 'apt update && apt install -y $apt_suggest'"
      echo "After installing 'sudo', add your user to the sudo group with:"
      echo "  su -c 'usermod -aG sudo $USER'"
      echo "Then log out and log back in to pick up the new group membership."
      echo
    fi
    ;;
  *)
    echo "Skipping apt installs. To install later run:" 
    echo "  sudo apt update && sudo apt install -y $apt_suggest"
    ;;
esac
 
info "Downloading archive..."
mkdir -p "$TARGET_DIR"
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

archive_file="$tmpdir/archive.tar.gz"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: Attempt release asset: curl -L -o $archive_file $RELEASE_ASSET_URL"
  echo "DRY RUN: Fallback branch archive: curl -L -o $archive_file $BRANCH_ARCHIVE_URL"
else
  # Try release asset first, fall back to branch archive
  if curl -L -o "$archive_file" --fail "$RELEASE_ASSET_URL"; then
    echo "Downloaded release asset: $RELEASE_ASSET_URL"
  else
    echo "Release asset not available; falling back to branch archive: $BRANCH_ARCHIVE_URL"
    curl -L -o "$archive_file" --fail "$BRANCH_ARCHIVE_URL"
  fi
fi

info "Extracting archive..."
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: mkdir -p $tmpdir/extracted && tar -tzf $archive_file | head -n 5"
else
  mkdir -p "$tmpdir/extracted"
  tar -xzf "$archive_file" -C "$tmpdir/extracted"
fi

# Find the extracted project directory (first directory in extracted)
if [ "$DRY_RUN" -eq 1 ]; then
  SRC_DIR="$tmpdir/extracted/<extracted-dir>"
else
  first_entry=$(find "$tmpdir/extracted" -maxdepth 1 -mindepth 1 -type d | head -n1)
  if [ -z "$first_entry" ]; then
    echo "Failed to find extracted directory." >&2
    exit 1
  fi
  SRC_DIR="$first_entry"
fi

info "Source directory: $SRC_DIR"
# Copy the extracted project into the target directory so editable installs
# reference a persistent path (avoid pip recording temporary locations).
DEST_EXTRACT="$TARGET_DIR/extracted"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: copy extracted project $SRC_DIR -> $DEST_EXTRACT"
else
  mkdir -p "$DEST_EXTRACT"
  # Use tar pipe to copy files preserving metadata without relying on rsync
  (cd "$SRC_DIR" && tar cf - .) | (cd "$DEST_EXTRACT" && tar xpf -)
  SRC_DIR="$DEST_EXTRACT"
fi

VENV_DIR="$TARGET_DIR/.venv"
info "Creating virtualenv at $VENV_DIR"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: python3 -m venv $VENV_DIR"
else
  python3 -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

info "Upgrading pip in virtualenv"
run_or_echo "$VENV_PY -m pip install --upgrade pip setuptools wheel"

# Prompt for extras
chosen_extras=""
prompt_extra() {
  name=$1
  if [ "$ASSUME_YES" -eq 1 ]; then
    choice=Y
  else
    printf "Enable extra '%s'? [Y/n]: " "$name"
    IFS= read -r choice || true
    choice=${choice:-Y}
  fi
  case "$choice" in
    [Yy]*)
      if [ -z "$chosen_extras" ]; then
        chosen_extras="$name"
      else
        chosen_extras="$chosen_extras,$name"
      fi
      ;;
    *) ;;
  esac
}

prompt_extra aprs
prompt_extra wspr
prompt_extra direwolf

extras_spec=""
if [ -n "$chosen_extras" ]; then
  extras_spec="[$chosen_extras]"
fi

echo "Installing package editable from source into virtualenv..."
echo "Extras: ${chosen_extras:-none}"

# Install local sibling packages under SRC_DIR/src/* first so internal
# dependencies (neo-core, neo-aprs, neo-wspr, etc.) are provided from the
# extracted tree rather than pulled from PyPI.
if [ -d "$SRC_DIR/src" ]; then
  info "Local packages found in $SRC_DIR/src:"
  ls -1 "$SRC_DIR/src" || true

  # Only consider directories that look like Python projects (have pyproject.toml or setup.py)
  pkgdirs=("$SRC_DIR/src"/*)
  py_pkgdirs=()
  for p in "${pkgdirs[@]}"; do
    if [ -d "$p" ] && ( [ -f "$p/pyproject.toml" ] || [ -f "$p/setup.py" ] ); then
      py_pkgdirs+=("$p")
    else
      warn "Skipping non-Python or non-packaged entry: $p"
    fi
  done

  # Build initial ordered list: prefer neo_core first to satisfy internal deps
  ordered=()
  for p in "${py_pkgdirs[@]}"; do
    bn=$(basename "$p")
    if [ "$bn" = "neo_core" ]; then
      ordered+=("$p")
    fi
  done
  for p in "${py_pkgdirs[@]}"; do
    bn=$(basename "$p")
    if [ "$bn" != "neo_core" ]; then
      ordered+=("$p")
    fi
  done

  # Iteratively attempt installs: if a package fails due to unmet local
  # dependency, retry remaining packages until none change (then fail).
  remain=("${ordered[@]}")
  while [ ${#remain[@]} -gt 0 ]; do
    changed=0
    next_remain=()
    for pkgpath in "${remain[@]}"; do
      if [ ! -d "$pkgpath" ]; then
        continue
      fi
      # Skip entries that are not Python projects
      if [ ! -f "$pkgpath/pyproject.toml" ] && [ ! -f "$pkgpath/setup.py" ]; then
        echo "Skipping non-Python package during install: $pkgpath"
        changed=1
        continue
      fi
      pkgname=$(basename "$pkgpath")
      info "Attempting local install: $pkgname"
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "DRY RUN: $VENV_PY -m pip install -e \"$pkgpath\" -v"
        changed=1
      else
        if "$VENV_PY" -m pip install -e "$pkgpath" -v; then
          changed=1
        else
          err "Local install failed for $pkgname; will retry after other installs."
          next_remain+=("$pkgpath")
        fi
      fi
    done
    if [ ${#next_remain[@]} -eq ${#remain[@]} ] && [ $changed -eq 0 ]; then
      echo "Could not make progress installing local packages; remaining:" >&2
      for p in "${next_remain[@]}"; do echo " - $p"; done
      exit 1
    fi
    remain=("${next_remain[@]}")
  done
fi

# Finally install the top-level package (with selected extras)
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: $VENV_PY -m pip install -e \"$SRC_DIR$extras_spec\""
else
  info "Installing top-level package with extras: ${chosen_extras:-none}"
  "$VENV_PY" -m pip install -e "$SRC_DIR$extras_spec"
fi

succ "Installation complete. Performing basic validation..."
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: $VENV_PY -m pip show neo_rx || true"
else
  "$VENV_PY" -m pip show neo_rx || true
fi

# Final user-facing quick-start instructions (printed last on success)
cat <<EOF
==================== Neo-RX Installation Complete ====================

Quick start — first steps (copy/paste):

  # Activate the virtualenv created by the installer
  . "$VENV_DIR/bin/activate"

  # Run the APRS onboarding wizard (renders configs and prompts)
  neo-rx aprs setup

  # Optional: run diagnostics to validate tools and hardware
  neo-rx aprs diagnostics --verbose

  # Smoke-test (receive-only, no APRS-IS uplink)
  neo-rx aprs listen --once --no-aprsis

  # Start the APRS listener (normal operation, will attempt APRS-IS uplink if configured)
  neo-rx aprs listen

View logs (tail while running):
  tail -f "$TARGET_DIR/logs/aprs/neo-rx.log"

If you used a custom --target-dir, replace the paths above accordingly.

To remove the installation:
  rm -rf "$VENV_DIR"
  rm -rf "$TARGET_DIR/extracted"

For help and other commands:
  neo-rx --help
  neo-rx aprs --help

=====================================================================
EOF

# mark the task done in todo list
_DONE=1

exit 0
