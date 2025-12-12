from types import SimpleNamespace


def test_score_band_and_scan_bands():
    from neo_wspr.wspr.scan import score_band, scan_bands

    spots = [
        {"call": "A", "snr_db": -10},
        {"call": "B", "snr_db": -5},
        {"call": "A", "snr_db": -8},
    ]

    metrics = score_band(spots, duration_s=60)
    assert metrics["band_decodes"] == 3
    assert metrics["decodes_per_min"] == 3.0
    assert metrics["median_snr_db"] in (-9, -8, -10)
    assert metrics["unique_calls"] == 2

    # scan_bands: two bands, second returns more spots so should sort first
    def cap1(band, dur):
        return ["2025-12-11 12:02:00 14095200 A FN20 10\n"]

    def cap2(band, dur):
        return [
            "2025-12-11 12:02:00 7056000 X FN20 5\n",
            "2025-12-11 12:02:00 7056000 Y FN20 6\n",
        ]

    reports = scan_bands([14095200, 7056000], lambda b, d: cap2(b, d) if b == 7056000 else cap1(b, d), 60)
    assert reports[0]["band_hz"] == 7056000
    assert reports[1]["band_hz"] == 14095200

    # invalid duration should raise in score_band
    try:
        score_band([], duration_s=0)
    except ValueError:
        pass
    else:
        assert False, "score_band should raise for non-positive duration"
from neo_wspr.wspr.scan import scan_bands


def fake_capture_band1(band_hz: int, duration_s: int):
    # two spots with SNRs -12 and -10
    return [
        "2025-11-08 12:34:00 14080000 K1ABC FN42 -12 0.5\n",
        "2025-11-08 12:36:00 14080000 K2DEF FN42 -10\n",
    ]


def fake_capture_band2(band_hz: int, duration_s: int):
    # no spots
    return []


def test_scan_bands_ranks_and_metrics():
    bands = [14080000, 7080000]

    def capture_fn(band, duration):
        return (
            fake_capture_band1(band, duration)
            if band == 14080000
            else fake_capture_band2(band, duration)
        )

    reports = scan_bands(bands, capture_fn, duration_s=120)
    assert len(reports) == 2
    # first report should be 14080000
    assert reports[0]["band_hz"] == 14080000
    assert reports[0]["band_decodes"] == 2
    assert reports[0]["median_snr_db"] == -11
    assert reports[1]["band_decodes"] == 0
