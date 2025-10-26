"""Tests for AX.25 to TNC2 conversion."""

from __future__ import annotations

import pytest

from nesdr_igate.aprs.ax25 import AX25DecodeError, kiss_payload_to_tnc2  # type: ignore[import]


def _encode_address(callsign: str, ssid: int = 0, *, last: bool, repeated: bool = False) -> bytes:
    callsign = callsign.ljust(6)[:6].upper()
    field = bytearray()
    for char in callsign:
        field.append(ord(char) << 1)
    byte = 0x60 | ((ssid & 0x0F) << 1)
    if repeated:
        byte |= 0x80
    if last:
        byte |= 0x01
    field.append(byte)
    return bytes(field)


def test_kiss_payload_to_tnc2_basic() -> None:
    payload = (
        _encode_address("APRS", last=False)
        + _encode_address("N0CALL", ssid=10, last=False)
        + _encode_address("WIDE1", ssid=1, last=False)
        + _encode_address("WIDE2", ssid=2, last=True, repeated=True)
        + bytes([0x03, 0xF0])
        + b"Hello APRS"
    )

    text = kiss_payload_to_tnc2(payload)
    assert text == "N0CALL-10>APRS,WIDE1-1,WIDE2-2*:Hello APRS"


def test_kiss_payload_invalid_control() -> None:
    payload = (
        _encode_address("APRS", last=False)
        + _encode_address("N0CALL", ssid=1, last=True)
        + bytes([0x00, 0xF0])
        + b"payload"
    )

    with pytest.raises(AX25DecodeError) as exc:
        kiss_payload_to_tnc2(payload)
    assert "Unsupported" in str(exc.value)
