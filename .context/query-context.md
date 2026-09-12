# SigMap Query Context
Generated: 2026-09-12T18:22:42.220Z

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

## docs/developer.md
```
h1 Install packages in dependency order
h1 from the repo root
h1 install only the wheels built from this repo
h1 install any runtime deps reported on import
h1 quick import checks
h1 CLI smoke
h1 Dry-run for version 0.2.8
h1 Build and create tags locally (no upload)
h1 Build, create tags, and upload to PyPI (requires credentials)
code-fence bash
code-fence plain
```

## docs/troubleshooting.md
```
h2 RTL-SDR Thermal Issues
h1 Before (thermal issues)
h1 After (stable)
h2 General Troubleshooting Tips
code-fence bash
code-fence plain
```

## tests/test_listen_command_extended.py
```
def test_resolve_direwolf_config_prefers_local(tmp_path) → None
def test_resolve_direwolf_config_fallback(tmp_path, monkeypatch) → None
def test_wait_for_kiss_success_after_retry(monkeypatch) → None
def test_wait_for_kiss_exhausts_attempts() → None
def test_display_frame_truncates_output(caplog) → None
def test_report_audio_error_logs_message(caplog) → None
def test_run_listen_config_missing(monkeypatch, tmp_path, caplog) → None
def test_run_listen_config_invalid(monkeypatch, tmp_path, caplog) → None
def test_run_listen_missing_direwolf_config(monkeypatch, tmp_path, caplog) → None
def test_run_listen_audio_capture_failure(monkeypatch, tmp_path, caplog) → None
def test_run_listen_direwolf_launch_failure(monkeypatch, tmp_path, caplog) → None
def test_run_listen_kiss_unreachable(monkeypatch, tmp_path, caplog) → None
def test_run_listen_receive_only_once(monkeypatch, tmp_path, caplog) → None
def test_apply_software_tocall_before_send(monkeypatch, tmp_path, caplog) → None
def test_run_listen_aprs_connect_failure(monkeypatch, tmp_path, caplog) → None
def test_run_listen_timeout_triggers_polling(monkeypatch, tmp_path, caplog) → None
def test_run_listen_kiss_client_error(monkeypatch, tmp_path, caplog) → None
def test_run_listen_skips_bad_frame(monkeypatch, tmp_path, caplog) → None
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
