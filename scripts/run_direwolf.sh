#!/usr/bin/env bash
# Launch Direwolf using rtl_fm as the audio source.
# The script expects a rendered Direwolf config file and ensures
# logs are captured under ~/.local/share/neo-igate/logs by default.

set -euo pipefail

CONFIG_PATH=${CONFIG_PATH:-$HOME/.config/neo-igate/direwolf.conf}
AUDIO_SAMPLE_RATE=${AUDIO_SAMPLE_RATE:-22050}
GAIN=${GAIN:-35}
FREQUENCY_HZ=${FREQUENCY_HZ:-144390000}
RTL_DEVICE_INDEX=${RTL_DEVICE_INDEX:-0}
RTL_PPM=${RTL_PPM:-0}
LOG_DIR=${LOG_DIR:-$HOME/.local/share/neo-igate/logs}
LOG_FILE=${LOG_FILE:-$LOG_DIR/direwolf.log}

usage() {
  cat <<EOF
Usage: $0 [config_path]

Environment overrides:
  CONFIG_PATH        Path to Direwolf config (default: ~/.config/neo-igate/direwolf.conf)
  AUDIO_SAMPLE_RATE  rtl_fm / Direwolf audio sample rate (default: 22050)
  FREQUENCY_HZ       Center frequency in Hz (default: 144390000)
  GAIN               RTL-SDR gain in dB or "auto" (default: 35)
  RTL_DEVICE_INDEX   rtl_fm device index (default: 0)
  RTL_PPM            Frequency correction in ppm (default: 0)
  LOG_DIR            Directory for Direwolf logs (default: ~/.local/share/neo-igate/logs)
  LOG_FILE           File to append Direwolf logs (default: LOG_DIR/direwolf.log)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ -n "${1:-}" ]]; then
  CONFIG_PATH=$1
fi

for cmd in rtl_fm direwolf; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command '$cmd' not found in PATH." >&2
    if [[ "$cmd" == "rtl_fm" ]]; then
      echo "Install via: sudo apt install rtl-sdr" >&2
    else
      echo "Install Direwolf via your package manager or https://github.com/wb2osz/direwolf" >&2
    fi
    exit 1
  fi
done

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Error: Direwolf config not found at $CONFIG_PATH" >&2
  echo "Render the template in docs/templates/direwolf.conf or rerun 'neo-igate setup'." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

echo "Starting rtl_fm + Direwolf pipeline..." >&2
trap 'echo "Stopping pipeline..." >&2; kill 0' INT TERM

{
  echo "---"
  echo "timestamp: $(date --iso-8601=seconds)"
  echo "frequency_hz: $FREQUENCY_HZ"
  echo "audio_sample_rate: $AUDIO_SAMPLE_RATE"
  echo "gain: $GAIN"
  echo "rtl_device_index: $RTL_DEVICE_INDEX"
  echo "rtl_ppm: $RTL_PPM"
} >>"$LOG_FILE"

# rtl_fm options: narrow FM, de-emphasis, fast AGC, 9 ksps output decimation
set +o pipefail
rtl_fm -d "$RTL_DEVICE_INDEX" -f "$FREQUENCY_HZ" -M fm -s "$AUDIO_SAMPLE_RATE" \
  -g "$GAIN" -p "$RTL_PPM" -E deemp -A fast -F 9 \
  | direwolf -c "$CONFIG_PATH" -r "$AUDIO_SAMPLE_RATE" -t 0 - \
  2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[1]:-0}
set -o pipefail

exit "$EXIT_CODE"
