from neo_igate.wspr.calibrate import estimate_offset_from_spots, compute_ppm_from_offset


def test_compute_ppm_from_offset_basic():
    # 1 kHz offset at 14.08 MHz -> ~0.0710 ppm
    freq = 14_080_000.0
    offset = 1000.0
    ppm = compute_ppm_from_offset(freq, offset)
    assert abs(ppm - (1000.0 / 14_080_000.0 * 1_000_000.0)) < 1e-6


def test_estimate_offset_from_spots_with_expected():
    spots = [
        {"freq_hz": 14_080_020.0, "snr_db": 10},
        {"freq_hz": 14_080_010.0, "snr_db": 12},
        {"freq_hz": 14_080_050.0, "snr_db": 8},
    ]
    expected = 14_080_000.0
    res = estimate_offset_from_spots(spots, expected)
    # median of freqs is 14080020.0
    assert res["count"] == 3
    assert res["median_observed_freq_hz"] == 14_080_020.0
    assert res["offset_hz"] == 20.0
    assert abs(res["ppm"] - compute_ppm_from_offset(expected, 20.0)) < 1e-9
