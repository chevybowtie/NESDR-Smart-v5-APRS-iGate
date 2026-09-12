from __future__ import annotations

import numpy as np

from neo_wspr.wspr.capture import _encode_iq_samples


def test_encode_iq_samples_accepts_numpy_complex_array() -> None:
    samples = np.array(
        [0.5 - 0.25j, -1.0 + 1.0j, 0.0 + 0.125j],
        dtype=np.complex64,
    )

    encoded = _encode_iq_samples(samples)

    expected = b"".join(
        int(value).to_bytes(2, "little", signed=True)
        for value in (
            16383,
            -8191,
            -32767,
            32767,
            0,
            4095,
        )
    )
    assert encoded == expected


def test_encode_iq_samples_preserves_sample_order_and_length() -> None:
    samples = np.array([0.25 + 0.5j, -0.5 - 0.25j], dtype=np.complex128)

    encoded = _encode_iq_samples(samples)

    assert len(encoded) == len(samples) * 4
    assert encoded == (
        int(8191).to_bytes(2, "little", signed=True)
        + int(16383).to_bytes(2, "little", signed=True)
        + int(-16383).to_bytes(2, "little", signed=True)
        + int(-8191).to_bytes(2, "little", signed=True)
    )
