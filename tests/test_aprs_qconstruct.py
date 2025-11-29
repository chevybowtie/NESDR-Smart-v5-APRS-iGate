"""Unit tests for APRS q-construct helper handling bytes input."""

from __future__ import annotations

from neo_aprs.commands.listen import _append_q_construct


def test_append_q_construct_bytes_adds_qhop() -> None:
    # Packet without existing q-construct should get qAR,<IGATE> appended
    tnc2 = b"KJ5EVH-7>APRS,WIDE1-1,WIDE2-1:PAYLOAD"
    result = _append_q_construct(tnc2, "KJ5EVH-10")
    assert isinstance(result, (bytes, bytearray))
    assert result == b"KJ5EVH-7>APRS,WIDE1-1,WIDE2-1,qAR,KJ5EVH-10:PAYLOAD"


def test_append_q_construct_bytes_existing_q_remains_unchanged() -> None:
    # Packet already containing a q-hop should be returned unchanged
    tnc2 = b"KJ5EVH-7>APRS,WIDE1-1,WIDE2-1,qAO,OTHERGATE:PAYLOAD"
    result = _append_q_construct(tnc2, "KJ5EVH-10")
    assert isinstance(result, (bytes, bytearray))
    assert result == tnc2
