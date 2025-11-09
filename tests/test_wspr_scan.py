from neo_igate.wspr.scan import scan_bands


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
        return fake_capture_band1(band, duration) if band == 14080000 else fake_capture_band2(band, duration)

    reports = scan_bands(bands, capture_fn, duration_s=120)
    assert len(reports) == 2
    # first report should be 14080000
    assert reports[0]["band_hz"] == 14080000
    assert reports[0]["band_decodes"] == 2
    assert reports[0]["median_snr_db"] == -11
    assert reports[1]["band_decodes"] == 0
