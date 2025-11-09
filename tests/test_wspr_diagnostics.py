from neo_igate.wspr.diagnostics import detect_upconverter_hint


def test_detect_upconverter_hint_from_spots():
    # Construct spots with a median observed frequency ~14_200_000
    spots = [
        {"freq_hz": 14_200_100.0},
        {"freq_hz": 14_200_000.0},
        {"freq_hz": 14_199_900.0},
    ]
    hint = detect_upconverter_hint(spots)
    # Observed median is ~14_200_000; nearest nominal 14_080_000 => diff ~120k
    assert hint["recommended_lo_offset_hz"] is not None
    assert hint["confidence"] > 0.0
