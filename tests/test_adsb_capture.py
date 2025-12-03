"""Tests for ADS-B capture functionality."""

import json
import tempfile
from pathlib import Path


from neo_adsb.adsb.capture import (
    AircraftState,
    CaptureStats,
    Dump1090Client,
    AdsbCapture,
    ADSB_FREQUENCY_HZ,
)


class TestAircraftState:
    """Tests for AircraftState dataclass."""

    def test_aircraft_state_defaults(self):
        """Test default values for AircraftState."""
        state = AircraftState(hex_id="ABC123")
        assert state.hex_id == "ABC123"
        assert state.flight is None
        assert state.altitude_ft is None
        assert state.ground_speed_kt is None
        assert state.latitude is None
        assert state.longitude is None
        assert state.messages == 0
        assert state.first_seen is not None
        assert state.last_seen is not None

    def test_aircraft_state_with_values(self):
        """Test AircraftState with all values."""
        state = AircraftState(
            hex_id="ABC123",
            flight="UAL123",
            altitude_ft=35000,
            ground_speed_kt=450.5,
            track_deg=180.0,
            latitude=37.7749,
            longitude=-122.4194,
            vertical_rate_fpm=-1000,
            squawk="1234",
            rssi_db=-25.5,
            messages=100,
        )
        assert state.flight == "UAL123"
        assert state.altitude_ft == 35000
        assert state.ground_speed_kt == 450.5
        assert state.latitude == 37.7749
        assert state.longitude == -122.4194
        assert state.squawk == "1234"
        assert state.messages == 100


class TestCaptureStats:
    """Tests for CaptureStats dataclass."""

    def test_capture_stats_defaults(self):
        """Test default values for CaptureStats."""
        stats = CaptureStats()
        assert stats.total_messages == 0
        assert stats.total_aircraft == 0
        assert stats.unique_aircraft == 0
        assert stats.max_range_nm == 0.0
        assert stats.max_altitude_ft == 0
        assert stats.start_time is not None


class TestDump1090Client:
    """Tests for Dump1090Client."""

    def test_client_creation(self):
        """Test client instantiation."""
        client = Dump1090Client()
        assert client.json_path == Path("/run/dump1090-fa/aircraft.json")
        assert client.poll_interval_s == 1.0

    def test_client_custom_path(self):
        """Test client with custom JSON path."""
        client = Dump1090Client(json_path="/custom/path/aircraft.json")
        assert client.json_path == Path("/custom/path/aircraft.json")

    def test_poll_missing_file(self):
        """Test poll when JSON file doesn't exist."""
        client = Dump1090Client(json_path="/nonexistent/aircraft.json")
        result = client.poll()
        assert result == []

    def test_poll_valid_json(self):
        """Test poll with valid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "now": 1700000000.0,
                "aircraft": [
                    {
                        "hex": "abc123",
                        "flight": "UAL123  ",
                        "alt_geom": 35000,
                        "gs": 450.5,
                        "track": 180.0,
                        "lat": 37.7749,
                        "lon": -122.4194,
                        "rssi": -25.5,
                        "messages": 100,
                    },
                    {
                        "hex": "def456",
                        "alt_baro": 25000,
                    },
                ]
            }, f)
            temp_path = f.name

        try:
            client = Dump1090Client(json_path=temp_path)
            aircraft = client.poll()

            assert len(aircraft) == 2

            # Check first aircraft
            ac1 = next(a for a in aircraft if a.hex_id == "ABC123")
            assert ac1.flight == "UAL123"
            assert ac1.altitude_ft == 35000
            assert ac1.ground_speed_kt == 450.5
            assert ac1.latitude == 37.7749
            assert ac1.longitude == -122.4194

            # Check second aircraft
            ac2 = next(a for a in aircraft if a.hex_id == "DEF456")
            assert ac2.altitude_ft == 25000
            assert ac2.flight is None
        finally:
            Path(temp_path).unlink()

    def test_poll_invalid_json(self):
        """Test poll with invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            client = Dump1090Client(json_path=temp_path)
            result = client.poll()
            assert result == []
        finally:
            Path(temp_path).unlink()

    def test_get_stats(self):
        """Test getting capture statistics."""
        client = Dump1090Client()
        stats = client.get_stats()
        assert isinstance(stats, CaptureStats)
        assert stats.total_messages == 0

    def test_clear_stale(self):
        """Test clearing stale aircraft."""
        client = Dump1090Client()
        # No aircraft to clear
        removed = client.clear_stale()
        assert removed == 0

    def test_get_aircraft(self):
        """Test getting specific aircraft."""
        client = Dump1090Client()
        # No aircraft yet
        result = client.get_aircraft("ABC123")
        assert result is None

    def test_get_all_aircraft(self):
        """Test getting all aircraft."""
        client = Dump1090Client()
        result = client.get_all_aircraft()
        assert result == []


class TestAdsbCapture:
    """Tests for AdsbCapture orchestrator."""

    def test_capture_creation(self):
        """Test capture instantiation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AdsbCapture(
                json_path="/run/dump1090-fa/aircraft.json",
                data_dir=Path(tmpdir),
            )
            assert capture._poll_interval_s == 1.0
            assert not capture.is_running()

    def test_capture_start_stop(self):
        """Test capture start and stop."""
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AdsbCapture(
                json_path="/nonexistent/aircraft.json",
                data_dir=Path(tmpdir),
                poll_interval_s=0.1,
            )

            capture.start()
            assert capture.is_running()

            capture.stop()
            assert not capture.is_running()

    def test_capture_double_start(self):
        """Test that double start is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AdsbCapture(
                json_path="/nonexistent/aircraft.json",
                data_dir=Path(tmpdir),
            )

            capture.start()
            capture.start()  # Should not raise
            assert capture.is_running()

            capture.stop()

    def test_capture_double_stop(self):
        """Test that double stop is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AdsbCapture(
                json_path="/nonexistent/aircraft.json",
                data_dir=Path(tmpdir),
            )

            capture.start()
            capture.stop()
            capture.stop()  # Should not raise
            assert not capture.is_running()

    def test_capture_callback(self):
        """Test callback registration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            capture = AdsbCapture(
                json_path="/nonexistent/aircraft.json",
                data_dir=Path(tmpdir),
            )

            callback_called = []

            def test_callback(aircraft_list):
                callback_called.append(len(aircraft_list))

            capture.add_callback(test_callback)
            assert len(capture._callbacks) == 1


class TestConstants:
    """Tests for module constants."""

    def test_adsb_frequency(self):
        """Test ADS-B frequency constant."""
        assert ADSB_FREQUENCY_HZ == 1_090_000_000
