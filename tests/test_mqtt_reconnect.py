"""Tests covering MQTT reconnect/backoff logic and CLI wiring."""

import types
from argparse import Namespace

import pytest

import neo_igate.telemetry.mqtt_publisher as mp


class MockClient:
    """Minimal paho-mqtt client stand-in with configurable failures."""

    def __init__(self, behavior=None):
        self.on_connect = None
        self.on_disconnect = None
        self._connect_calls = 0
        self._publish_calls = []
        self._behavior = behavior or {}

    def connect(self, host, port):
        self._connect_calls += 1
        fail_times = self._behavior.get("connect_fail_times", 0)
        if self._connect_calls <= fail_times:
            raise RuntimeError("simulated connect failure")
        if callable(self.on_connect):
            self.on_connect(self, None, None, 0)

    def loop_start(self):
        return None

    def loop_stop(self):
        return None

    def disconnect(self):
        return None

    def publish(self, topic, body):
        self._publish_calls.append((topic, body))
        fail_times = self._behavior.get("publish_fail_times", 0)
        if len(self._publish_calls) <= fail_times:
            raise RuntimeError("simulated publish failure")
        return None


def _patch_client(monkeypatch, behavior):
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: MockClient(behavior=behavior)))


def test_connect_eventually_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr(mp.time, "sleep", lambda _x: None)
    _patch_client(monkeypatch, {"connect_fail_times": 2})

    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    pub.connect()

    assert pub._connected is True
    assert pub._client._connect_calls == 3


def test_connect_exhausts_retries(monkeypatch, tmp_path):
    monkeypatch.setattr(mp.time, "sleep", lambda _x: None)
    _patch_client(monkeypatch, {"connect_fail_times": 10})

    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    pub._max_retries = 3
    pub._initial_backoff = 0

    with pytest.raises(RuntimeError):
        pub.connect()


def test_publish_retries_after_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(mp.time, "sleep", lambda _x: None)
    _patch_client(monkeypatch, {"publish_fail_times": 1})

    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    pub.connect()
    assert pub._connected is True

    pub.publish("neo_igate/wspr/spots", {"call": "K1ABC"})
    assert len(pub._client._publish_calls) >= 2


def test_cli_publisher_wiring(monkeypatch):
    from neo_igate import config as config_module
    from neo_igate.commands import wspr as wspr_cmd

    cfg = config_module.StationConfig(
        callsign="N0TEST",
        passcode="P",
        mqtt_enabled=True,
        mqtt_topic="neo_igate/wspr/spots",
        wspr_bands_hz=[14_080_000],
        wspr_capture_duration_s=1,
    )
    monkeypatch.setattr(config_module, "load_config", lambda path=None: cfg)

    published = []

    def publish(topic, payload):
        published.append((topic, payload))

    mock_pub = types.SimpleNamespace(
        connect=lambda: None,
        publish=publish,
        close=lambda: None,
        topic=None,
    )
    monkeypatch.setattr(wspr_cmd, "make_publisher_from_config", lambda _cfg: mock_pub)

    class StubCapture:
        def __init__(self, *args, **kwargs):
            self.publisher = kwargs.get('publisher')
            self.bands_hz = kwargs.get('bands_hz', [14_080_000])

        def start(self):
            # Simulate publishing spots
            from neo_igate.wspr.decoder import WsprDecoder
            decoder = WsprDecoder()
            for spot in decoder.run_wsprd_subprocess(b'', self.bands_hz[0]):
                if self.publisher:
                    topic = getattr(self.publisher, "topic", "neo_igate/wspr/spots")
                    self.publisher.publish(topic, spot)

        def stop(self):
            return None

        def is_running(self):
            return False  # Return False so the loop exits immediately

    monkeypatch.setattr(wspr_cmd, "WsprCapture", StubCapture)

    import neo_igate.wspr.decoder as decoder_mod

    def fake_run(self, iq_data, band_hz):
        yield {"spot": 1}
        yield {"spot": 2}

    monkeypatch.setattr(decoder_mod.WsprDecoder, "run_wsprd_subprocess", fake_run)

    args = Namespace(
        start=True,
        config=None,
        scan=False,
        json=False,
        diagnostics=False,
        calibrate=False,
        expected_freq=None,
        apply=False,
        write_config=False,
        spots_file=None,
        upload=False,
        mqtt=None,
    )

    result = wspr_cmd.run_wspr(args)

    assert result == 0
    assert len(published) == 2
    assert all(topic == cfg.mqtt_topic for topic, _payload in published)
