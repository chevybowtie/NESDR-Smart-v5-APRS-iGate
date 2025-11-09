import pathlib

from neo_igate.wspr.decoder import WsprDecoder


def test_parse_wsprd_fixture():
    fixture = pathlib.Path("tests/fixtures/wsprd_output.txt").read_text(encoding="utf-8")
    decoder = WsprDecoder()
    spots = list(decoder.decode_stream(fixture.splitlines()))
    assert len(spots) == 2
    first = spots[0]
    assert first["call"] == "K1ABC"
    assert first["grid"] == "FN42"
    assert first["freq_hz"] == 14080000
    assert isinstance(first["snr_db"], int)
    assert spots[1]["call"] == "G4XYZ"
