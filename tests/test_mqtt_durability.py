"""Durability tests: ensure OnDiskQueue persists across restarts and drains."""
import json
import types
from pathlib import Path

import pytest

import neo_rx.telemetry.mqtt_publisher as mp


class MockClient:
    def __init__(self, behavior=None):
        self.on_connect = None
        self.on_disconnect = None
        self._publish_calls = []
        self._behavior = behavior or {}
        self._connect_calls = 0
        self._attempts = 0

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
        # count attempts separately so failed attempts do not appear in
        # `_publish_calls` (we only record successful publishes)
        self._attempts += 1
        pub_fail = self._behavior.get("publish_fail_times", 0)
        if self._attempts <= pub_fail:
            raise RuntimeError("simulated publish failure")
        self._publish_calls.append((topic, body))
        return None


def test_queue_persists_across_restart(monkeypatch, tmp_path):
    """Messages enqueued before restart are published after restart."""
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)

    # Use a publisher to enqueue messages (no connect)
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: MockClient()))
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    pub.publish("neo_rx/wspr/spot", {"n": 1})
    pub.publish("neo_rx/wspr/spot", {"n": 2})

    queue_dir = tmp_path / "queue"
    files = list(queue_dir.glob("*.json"))
    assert len(files) == 2

    # Simulate restart: new publisher should drain queue on connect
    mock = MockClient()
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: mock))
    new_pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    new_pub.connect()

    # both messages should have been published and queue emptied
    assert len(mock._publish_calls) == 2
    assert not list(queue_dir.glob("*.json"))


def test_partial_delivery_on_restart_leaves_failed(monkeypatch, tmp_path):
    """If some publishes fail during drain, failed messages remain in queue."""
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)

    # Enqueue three messages
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: MockClient()))
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    for i in range(3):
        pub.publish(f"neo_rx/test/{i}", {"msg": i})

    # Simulate restart with a client that will fail on the first publish only
    behavior = {"publish_fail_times": 1}
    mock = MockClient(behavior=behavior)
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: mock))

    new_pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    new_pub.connect()

    # One publish failed and should remain; the other two should have been sent
    # Since the failing message is processed in file order, one file should remain
    queue_files = sorted((tmp_path / "queue").glob("*.json"))
    assert len(queue_files) == 1
    # Ensure total published calls equals 2 (the successful ones)
    assert len(mock._publish_calls) == 2
