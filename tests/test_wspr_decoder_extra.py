import os
import stat
import tempfile
import shutil

from neo_wspr.wspr.decoder import WsprDecoder


def test_parse_line_variants():
    d = WsprDecoder(options={})
    # with drift
    line = "2020-01-01 12:00:00 14097400 N0CALL FN31 12 0.5"
    spot = d._parse_line(line)
    assert spot["timestamp"] == "2020-01-01T12:00:00Z"
    assert spot["freq_hz"] == 14097400
    assert spot["call"] == "N0CALL"
    assert spot["grid"] == "FN31"
    assert spot["snr_db"] == 12
    assert abs(spot["drift"] - 0.5) < 1e-9

    # without drift
    line2 = "2020-01-01 12:00:00 14097400 N1ABC EN50 -3"
    spot2 = d._parse_line(line2)
    assert spot2["drift"] is None

    # malformed line -> None
    assert d._parse_line("") is None
    assert d._parse_line("not a valid line") is None


def test_decode_stream_bytes_and_strings():
    d = WsprDecoder()
    chunks = [
        b"2020-01-01 12:00:00 14097400 B1 FN31 5\n2020-01-01 12:01:00 14097400 B2 FN32 6\n",
        "2020-01-01 12:02:00 14097400 B3 FN33 7\n",
    ]
    results = list(d.decode_stream(chunks))
    assert len(results) == 3
    assert results[0]["call"] == "B1"
    assert results[1]["call"] == "B2"
    assert results[2]["call"] == "B3"


def test_run_wsprd_subprocess_with_fake_executable():
    # create a fake wsprd script that prints a valid spot line and some stderr
    tmpdir = tempfile.mkdtemp()
    try:
        script_path = os.path.join(tmpdir, "fake_wsprd")
        with open(script_path, "w", encoding="utf-8") as fh:
            fh.write("#!/usr/bin/env python3\n")
            fh.write("import sys\n")
            fh.write("sys.stdout.write('2020-01-01 12:00:00 14097400 FX1 FN31 10\\n')\n")
            fh.write("sys.stderr.write('fake stderr line\\n')\n")
        # make executable
        os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IXUSR)

        d = WsprDecoder()
        # override wsprd_path to our fake script
        d.wsprd_path = script_path

        # small iq_data
        iq = b"\x00\x01\x02\x03" * 1024
        spots = list(d.run_wsprd_subprocess(iq, band_hz=14097400))
        assert len(spots) == 1
        s = spots[0]
        assert s["call"] == "FX1"
        assert s["grid"] == "FN31"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
