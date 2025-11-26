"""Utilities for decoding AX.25 frames carried inside KISS payloads."""

from __future__ import annotations

from dataclasses import dataclass


class AX25DecodeError(ValueError):
    """Raised when a KISS payload cannot be decoded into a TNC2 frame."""


@dataclass(slots=True)
class AX25Address:
    """Represents a single AX.25 address field extracted from a frame."""

    callsign: str
    ssid: int
    has_been_repeated: bool

    def to_tnc2(self, include_asterisk: bool = False) -> str:
        """Render the address into TNC2 text form.

        Args:
            include_asterisk: Whether to include a trailing `*` for digipeaters.

        Returns:
            Normalised callsign string with optional SSID and asterisk.
        """
        suffix = f"-{self.ssid}" if self.ssid > 0 else ""
        indicator = "*" if include_asterisk and self.has_been_repeated else ""
        return f"{self.callsign}{suffix}{indicator}"


def kiss_payload_to_tnc2(payload: bytes) -> bytes:
    """Convert a raw AX.25 frame (from a KISS payload) to TNC2 textual form.
    
    Returns bytes to preserve binary info fields that may contain non-UTF-8 data.
    The frame is: src>dest[,path]:info where info may be binary.
    """
    if len(payload) < 16:
        raise AX25DecodeError("AX.25 frame too short")

    addresses, offset = _parse_address_fields(payload)
    if len(addresses) < 2:
        raise AX25DecodeError("AX.25 frame missing source/destination addresses")

    if offset + 2 > len(payload):
        raise AX25DecodeError("AX.25 frame missing control/PID fields")

    control = payload[offset]
    pid = payload[offset + 1]
    info = payload[offset + 2 :]

    if control != 0x03 or pid != 0xF0:
        raise AX25DecodeError(
            f"Unsupported AX.25 frame type control={control:#x} pid={pid:#x}"
        )

    dest = addresses[0]
    src = addresses[1]
    digis = addresses[2:]

    path_parts: list[str] = []
    for index, digi in enumerate(digis):
        path_parts.append(digi.to_tnc2(include_asterisk=True))

    dest_text = dest.to_tnc2()
    src_text = src.to_tnc2()
    path_suffix = f",{','.join(path_parts)}" if path_parts else ""
    
    # Preserve binary info field - convert text parts to bytes and concatenate
    header_text = f"{src_text}>{dest_text}{path_suffix}:"
    header_bytes = header_text.encode("ascii")
    
    # Truncate info at first CR or LF to ensure only one line is sent to APRS-IS.
    # APRS-IS expects single-line packets terminated by CR+LF. Any embedded CR/LF
    # in the info field should be treated as the end of the packet line.
    for sep in (b"\r", b"\n"):
        idx = info.find(sep)
        if idx >= 0:
            info = info[:idx]
            break
    
    return header_bytes + info


def _parse_address_fields(payload: bytes) -> tuple[list[AX25Address], int]:
    """Decode the chained AX.25 address blocks from a KISS payload."""
    addresses: list[AX25Address] = []
    offset = 0
    while offset + 7 <= len(payload):
        field = payload[offset : offset + 7]
        offset += 7
        callsign = _decode_callsign(field[:6])
        ssid = (field[6] >> 1) & 0x0F
        has_been_repeated = bool(field[6] & 0x80)
        addresses.append(
            AX25Address(
                callsign=callsign, ssid=ssid, has_been_repeated=has_been_repeated
            )
        )
        if field[6] & 0x01:
            break
    else:
        raise AX25DecodeError("AX.25 address extension bit not found")

    return addresses, offset


def _decode_callsign(raw: bytes) -> str:
    """Convert a padded AX.25 callsign field to an uppercase string."""
    chars = []
    for byte in raw:
        value = (byte >> 1) & 0x7F
        if value == 0x20:  # padding space
            chars.append(" ")
        elif value != 0:
            chars.append(chr(value))
    return "".join(chars).strip().upper()
