import types

import pytest

import neo_igate.telemetry.mqtt_publisher as mp


class MockClient:
    def __init__(self, behavior=None):
        # behavior: dict to configure connect failures and publish behavior
        self.on_connect = None
        self.on_disconnect = None
        self._connect_calls = 0
        self._publish_calls = []
        self._behavior = behavior or {}

    def connect(self, host, port):
        self._connect_calls += 1
        # simulate configured failure counts
        fail_times = self._behavior.get("connect_fail_times", 0)
        if self._connect_calls <= fail_times:
            raise RuntimeError("simulated connect failure")
        # otherwise call on_connect callback with rc=0
        if callable(self.on_connect):
            # (client, userdata, flags, rc)
            self.on_connect(self, None, None, 0)

    def loop_start(self):
        return None

    def loop_stop(self):
        return None

    def disconnect(self):
        return None

    def publish(self, topic, body):
        self._publish_calls.append((topic, body))
        pub_fail = self._behavior.get("publish_fail_times", 0)
        if len(self._publish_calls) <= pub_fail:
            raise RuntimeError("simulated publish failure")
        return None


def test_connect_retries_and_succeeds(monkeypatch):
    # Patch time.sleep to avoid actual delays
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)

    behavior = {"connect_fail_times": 2}
    # Replace the mqtt module used by the publisher with a simple namespace
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: MockClient(behavior=behavior)))

    pub = mp.MqttPublisher(host="fake", port=1883)
    # Should not raise despite initial connect failures
    pub.connect()
    assert pub._connected is True


def test_publish_retries_after_failure(monkeypatch):
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)

    # Behavior: connect succeeds immediately, publish fails once then succeeds
    behavior = {"connect_fail_times": 0, "publish_fail_times": 1}
    mock = MockClient(behavior=behavior)
    # replace the mqtt module to return our mock instance
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: mock))

    pub = mp.MqttPublisher(host="fake", port=1883)
    pub.connect()
    assert pub._connected is True

    # First publish will raise inside MockClient, code should attempt reconnect and retry
    pub.publish("neo_igate/wspr/spots", {"call": "K1ABC"})
    # ensure two publish attempts were recorded
    assert len(mock._publish_calls) >= 2
