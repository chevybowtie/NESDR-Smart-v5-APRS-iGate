#!/usr/bin/env bash
set -euo pipefail

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

# Ensure python3 and venv helper exist (but do not apt-install automatically)
echo "Installer target directory: $TARGET_DIR"

echo "Attempting release asset first, then falling back to branch archive if needed."

apt_suggest="python3 python3-venv curl tar"
optional_pkgs="rtl-sdr direwolf sox"

echo "The system packages suggested for Debian 13 are: $apt_suggest"
echo "Optional packages for SDR/APRS use: $optional_pkgs"
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
        echo "Note: your user '$USER' is not in the 'sudo' group. To gain sudo rights run as root: 'usermod -aG sudo $USER' and then re-login." 
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
        echo "Running: $cmd"
        bash -c "$cmd"
      fi
    else
      echo
      echo "Warning: 'sudo' not found on this system. The installer cannot run apt commands automatically."
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
 
echo "Downloading archive..."
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

echo "Extracting archive..."
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

echo "Source directory: $SRC_DIR"

VENV_DIR="$TARGET_DIR/.venv"
echo "Creating virtualenv at $VENV_DIR"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: python3 -m venv $VENV_DIR"
else
  python3 -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

echo "Upgrading pip in virtualenv"
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
  echo "Local packages found in $SRC_DIR/src:"
  ls -1 "$SRC_DIR/src" || true

  # Build initial ordered list: prefer neo_core first to satisfy internal deps
  pkgdirs=("$SRC_DIR/src"/*)
  ordered=()
  for p in "${pkgdirs[@]}"; do
    bn=$(basename "$p")
    if [ "$bn" = "neo_core" ]; then
      ordered+=("$p")
    fi
  done
  for p in "${pkgdirs[@]}"; do
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
      pkgname=$(basename "$pkgpath")
      echo "Attempting local install: $pkgname"
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "DRY RUN: $VENV_PY -m pip install -e \"$pkgpath\" -v"
        changed=1
      else
        if "$VENV_PY" -m pip install -e "$pkgpath" -v; then
          changed=1
        else
          echo "Local install failed for $pkgname; will retry after other installs." >&2
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
  "$VENV_PY" -m pip install -e "$SRC_DIR$extras_spec"
fi

echo "Installation complete. Performing basic validation..."
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY RUN: $VENV_PY -m pip show neo_rx || true"
else
  "$VENV_PY" -m pip show neo_rx || true
fi

echo "Next steps:"
echo " - Render Direwolf config: $VENV_DIR/bin/neo-rx aprs setup"
echo " - Start Direwolf helper: scripts/run_direwolf.sh"
echo " - To remove the virtualenv: rm -rf $VENV_DIR"

exit 0
