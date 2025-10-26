#!/usr/bin/env bash
# Capture IQ and audio samples from the NESDR Smart v5 for testing.

set -euo pipefail

for cmd in rtl_sdr rtl_fm; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Error: required command '${cmd}' not found in PATH." >&2
    echo "Install via your package manager. On Debian/Ubuntu:" >&2
    echo "  sudo apt update && sudo apt install rtl-sdr" >&2
    exit 1
  fi
done

SOX_AVAILABLE=true
if ! command -v sox >/dev/null 2>&1; then
  SOX_AVAILABLE=false
  echo "Warning: 'sox' not found. WAV conversion will be skipped." >&2
fi

FREQUENCY_HZ=${FREQUENCY_HZ:-144390000}
IQ_SAMPLE_RATE=${IQ_SAMPLE_RATE:-250000}
AUDIO_SAMPLE_RATE=${AUDIO_SAMPLE_RATE:-22050}
GAIN=${GAIN:-35}
DURATION=${DURATION:-120}
OUTPUT_DIR=${OUTPUT_DIR:-samples}
RTL_DEVICE_INDEX=${RTL_DEVICE_INDEX:-0}
RTL_PPM=${RTL_PPM:-0}

IQ_OUTPUT="${OUTPUT_DIR}/nesdr_aprs_${FREQUENCY_HZ}_iq.raw"
AUDIO_OUTPUT_RAW="${OUTPUT_DIR}/nesdr_aprs_${FREQUENCY_HZ}_audio.raw"
AUDIO_OUTPUT_WAV="${OUTPUT_DIR}/nesdr_aprs_${FREQUENCY_HZ}_audio.wav"
SUMMARY_FILE="${OUTPUT_DIR}/capture_summary.txt"
AUDIO_BYTES=$((AUDIO_SAMPLE_RATE * DURATION * 2)) # 16-bit (2 bytes) mono samples

mkdir -p "${OUTPUT_DIR}"

echo "Capturing ${DURATION}s of IQ data at ${IQ_SAMPLE_RATE} sps to ${IQ_OUTPUT}" >&2
# Note: rtl_sdr prints "User cancel" when it finishes after reading -n samples.
rtl_sdr -d "${RTL_DEVICE_INDEX}" -f "${FREQUENCY_HZ}" -s "${IQ_SAMPLE_RATE}" \
  -g "${GAIN}" -p "${RTL_PPM}" -n "$((IQ_SAMPLE_RATE * DURATION))" "${IQ_OUTPUT}"

echo "Capturing ${DURATION}s of demodulated audio at ${AUDIO_SAMPLE_RATE} sps" >&2
echo "NOTE: rtl_fm outputs 16-bit little-endian PCM" >&2
# Expect rtl_fm to report "User cancel" after the pipeline finishes collecting the desired duration.
set +o pipefail
if [ "${SOX_AVAILABLE}" = true ]; then
  rtl_fm -d "${RTL_DEVICE_INDEX}" -f "${FREQUENCY_HZ}" -M fm -s "${AUDIO_SAMPLE_RATE}" \
    -g "${GAIN}" -p "${RTL_PPM}" -E deemp -A fast -F 9 \
    | head -c "${AUDIO_BYTES}" \
    | tee "${AUDIO_OUTPUT_RAW}" \
    | sox -t raw -r "${AUDIO_SAMPLE_RATE}" -es -b 16 -c 1 -V1 - "${AUDIO_OUTPUT_WAV}"
else
  rtl_fm -d "${RTL_DEVICE_INDEX}" -f "${FREQUENCY_HZ}" -M fm -s "${AUDIO_SAMPLE_RATE}" \
    -g "${GAIN}" -p "${RTL_PPM}" -E deemp -A fast -F 9 \
    | head -c "${AUDIO_BYTES}" \
    > "${AUDIO_OUTPUT_RAW}"
fi
set -o pipefail

echo "Capture complete. Files:" >&2
if [ "${SOX_AVAILABLE}" = true ]; then
  ls -lh "${IQ_OUTPUT}" "${AUDIO_OUTPUT_RAW}" "${AUDIO_OUTPUT_WAV}" >&2
else
  ls -lh "${IQ_OUTPUT}" "${AUDIO_OUTPUT_RAW}" >&2
fi

{
  echo "timestamp: $(date --iso-8601=seconds)"
  echo "frequency_hz: ${FREQUENCY_HZ}"
  echo "iq_sample_rate: ${IQ_SAMPLE_RATE}"
  echo "audio_sample_rate: ${AUDIO_SAMPLE_RATE}"
  echo "gain: ${GAIN}"
  echo "duration_s: ${DURATION}"
  echo "rtl_device_index: ${RTL_DEVICE_INDEX}"
  echo "rtl_ppm: ${RTL_PPM}"
} >> "${SUMMARY_FILE}"
