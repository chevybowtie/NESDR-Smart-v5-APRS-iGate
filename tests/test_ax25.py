"""Tests for AX.25 to TNC2 conversion."""

from __future__ import annotations

import pytest

from neo_igate.aprs.ax25 import AX25DecodeError, kiss_payload_to_tnc2  # type: ignore[import]


def _encode_address(
    callsign: str, ssid: int = 0, *, last: bool, repeated: bool = False
) -> bytes:
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
    assert text == b"N0CALL-10>APRS,WIDE1-1,WIDE2-2*:Hello APRS"


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


def test_kiss_payload_to_tnc2_preserves_binary_info() -> None:
    """Verify that non-UTF-8 binary data in info field is preserved."""
    payload = (
        _encode_address("APRS", last=False)
        + _encode_address("N0CALL", last=True)
        + bytes([0x03, 0xF0])
        # Info field with invalid UTF-8 sequence
        + b"Binary\xff\xfe\xfddata"
    )

    result = kiss_payload_to_tnc2(payload)
    assert result == b"N0CALL>APRS:Binary\xff\xfe\xfddata"
    # Verify it's bytes and preserves the exact binary sequence
    assert isinstance(result, bytes)
    assert b"\xff\xfe\xfd" in result


def test_kiss_payload_to_tnc2_truncates_at_cr() -> None:
    """Verify that info field is truncated at first CR character."""
    payload = (
        _encode_address("APRS", last=False)
        + _encode_address("N0CALL", last=True)
        + bytes([0x03, 0xF0])
        # Info field with embedded CR - should be truncated here
        + b"First line\rSecond line"
    )

    result = kiss_payload_to_tnc2(payload)
    # Only the part before CR should be included
    assert result == b"N0CALL>APRS:First line"
    assert b"Second line" not in result


def test_kiss_payload_to_tnc2_truncates_at_lf() -> None:
    """Verify that info field is truncated at first LF character."""
    payload = (
        _encode_address("APRS", last=False)
        + _encode_address("N0CALL", last=True)
        + bytes([0x03, 0xF0])
        # Info field with embedded LF - should be truncated here
        + b"First line\nSecond line"
    )

    result = kiss_payload_to_tnc2(payload)
    # Only the part before LF should be included
    assert result == b"N0CALL>APRS:First line"
    assert b"Second line" not in result


def test_kiss_payload_to_tnc2_truncates_at_crlf() -> None:
    """Verify that info field is truncated at first CR in CRLF sequence."""
    payload = (
        _encode_address("APRS", last=False)
        + _encode_address("N0CALL", last=True)
        + bytes([0x03, 0xF0])
        # Info field with embedded CRLF - should truncate at CR
        + b"First line\r\nSecond line"
    )

    result = kiss_payload_to_tnc2(payload)
    # Only the part before CRLF should be included (truncates at first CR)
    assert result == b"N0CALL>APRS:First line"
    assert b"Second line" not in result
    assert b"\r" not in result
