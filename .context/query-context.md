# SigMap Query Context
Generated: 2026-09-12T19:07:10.865Z

## docs/diagnostics.md
```
h1 Diagnostics Command Outline
h2 Command Summary
h2 Device Discovery
h2 Checks Performed (Common)
h3 1. Environment
h3 2. Configuration Validation
h3 3. SDR Hardware
h2 ADS-B-Specific Checks
h3 4. Decoder (readsb/dump1090)
h3 5. RTL-SDR Availability
h3 6. ADS-B Exchange Integration
h2 APRS-Specific Checks
h3 7. Direwolf / KISS
h3 8. APRS-IS Uplink
h2 WSPR-Specific Checks
h3 7. Decoder Binary
h3 8. Upconverter Detection
h2 Configuration & Paths (All Modes)
h3 9. Configuration & Paths
h2 Output Schema
```

## tests/test_wspr_calibrate.py
```
class TestComputePpmFromOffset
def test_positive_offset()
def test_negative_offset()
def test_zero_freq_raises()
class TestApplyPpmToRadio
def test_successful_application(mock_rtlsdr_cls)
def test_no_devices_found(mock_rtlsdr_cls)
def test_import_error()
def mock_import(name, *args, **kwargs)
def test_device_error(mock_rtlsdr_cls)
class TestPersistPpmToConfig
def test_successful_persist(mock_config)
class TestEstimateOffsetFromSpots
def test_with_expected_freq()
def test_without_expected_freq()
def test_no_freqs_raises()
def test_skips_invalid_freq()
class TestLoadSpotsFromJsonl
def test_load_valid_file()
def test_file_not_found()
```

## tests/test_wspr_capture_publish.py
```
class MockPublisher
def __init__()
def connect()
def publish(topic, payload)
def close()
def fake_capture_fn(band_hz: int, duration_s: int)
def test_capture_publishes(tmp_path: Path)
```

## tests/test_wspr_capture.py
```
class DummyUploader
def __init__() → None
def enqueue_spot(spot: dict) → None
def fake_capture_fn(band_hz: int, duration_s: int)
def test_run_capture_cycle_enriches_spots(tmp_path: Path)
def test_capture_enqueues_when_metadata_present(tmp_path: Path)
def test_capture_skips_enqueue_without_grid(tmp_path: Path)
```

## tests/test_wspr_uploader.py
```
class DummyResponse
def __init__(status_code, text) → None
class DummySession
def __init__(response: DummyResponse) → None
def get(url, params, timeout)
class FakeClock
def __init__(start: float) → None
def advance(seconds: float) → None
def sample_spot(**overrides)
def test_enqueue_spot_creates_queue_file(tmp_path: Path)
def test_read_queue_empty(tmp_path: Path)
def test_read_queue_multiple_items(tmp_path: Path)
def test_rewrite_queue_replaces_atomically(tmp_path: Path)
def test_drain_empty_queue()
def test_drain_all_succeed(tmp_path: Path, monkeypatch)
def test_drain_partial_failure(tmp_path: Path, monkeypatch)
def test_drain_max_items_limit(tmp_path: Path, monkeypatch)
def test_drain_exception_handling(tmp_path: Path, monkeypatch)
def test_upload_spot_success_builds_params(tmp_path: Path)
def test_upload_spot_missing_metadata_skips_request(tmp_path: Path)
```
