"""Tests for MQTT publisher on-disk buffering."""
import json
import tempfile
import types
from pathlib import Path

import pytest

import neo_igate.telemetry.mqtt_publisher as mp


class MockClient:
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
        pub_fail = self._behavior.get("publish_fail_times", 0)
        if len(self._publish_calls) <= pub_fail:
            raise RuntimeError("simulated publish failure")
        return None


def test_buffer_message_when_not_connected(monkeypatch, tmp_path):
    """When disconnected, messages should be buffered to disk."""
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)
    
    # Client that never connects
    behavior = {"connect_fail_times": 999}
    monkeypatch.setattr(
        mp, "mqtt", types.SimpleNamespace(Client=lambda: MockClient(behavior=behavior))
    )
    
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    
    # Don't call connect, so we're not connected
    # Publish should buffer the message
    pub.publish("neo_igate/wspr/spots", {"call": "K1ABC"})
    
    buffer_file = tmp_path / "mqtt_buffer.jsonl"
    assert buffer_file.exists()
    
    lines = buffer_file.read_text().splitlines()
    assert len(lines) == 1
    
    record = json.loads(lines[0])
    assert record["topic"] == "neo_igate/wspr/spots"
    assert "K1ABC" in record["body"]


def test_drain_buffer_on_connect(monkeypatch, tmp_path):
    """When connection is established, buffered messages should be sent."""
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)
    
    # Create a buffer with one message
    buffer_file = tmp_path / "mqtt_buffer.jsonl"
    buffer_file.write_text(
        json.dumps({"topic": "neo_igate/wspr/spots", "body": '{"call":"K1ABC"}', "ts": 1234567890})
        + "\n"
    )
    
    mock = MockClient()
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: mock))
    
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    pub.connect()
    
    # Buffer should be drained and file should be removed
    assert not buffer_file.exists()
    assert len(mock._publish_calls) == 1
    assert mock._publish_calls[0][0] == "neo_igate/wspr/spots"


def test_buffer_rotation_at_capacity(monkeypatch, tmp_path):
    """When buffer reaches max size, oldest messages should be dropped."""
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)
    
    behavior = {"connect_fail_times": 999}
    monkeypatch.setattr(
        mp, "mqtt", types.SimpleNamespace(Client=lambda: MockClient(behavior=behavior))
    )
    
    # Small buffer size for testing
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path, max_buffer_size=3)
    
    # Publish 5 messages while disconnected
    for i in range(5):
        pub.publish("neo_igate/test", {"msg": i})
    
    buffer_file = tmp_path / "mqtt_buffer.jsonl"
    lines = buffer_file.read_text().splitlines()
    
    # Should only have 3 messages (last 3)
    assert len(lines) == 3
    
    # Verify we kept the newest messages
    records = [json.loads(line) for line in lines]
    msgs = [json.loads(r["body"])["msg"] for r in records]
    assert msgs == [2, 3, 4]


def test_partial_drain_on_publish_failure(monkeypatch, tmp_path):
    """If some buffered messages fail to publish, they should remain in buffer."""
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)
    
    # Create buffer with 3 messages
    buffer_file = tmp_path / "mqtt_buffer.jsonl"
    messages = [
        json.dumps({"topic": f"neo_igate/test/{i}", "body": f'{{"msg":{i}}}', "ts": 1234567890 + i})
        for i in range(3)
    ]
    buffer_file.write_text("\n".join(messages) + "\n")
    
    # Mock client that fails on 2nd and 3rd publish
    behavior = {"publish_fail_times": 2}
    mock = MockClient(behavior=behavior)
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: mock))
    
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    pub.connect()
    
    # Buffer should still exist with failed messages
    assert buffer_file.exists()
    remaining = buffer_file.read_text().splitlines()
    # First message succeeded, 2nd and 3rd failed, so we should have 2 remaining
    assert len(remaining) == 2


def test_buffer_dir_creation(monkeypatch, tmp_path):
    """Buffer directory should be created if it doesn't exist."""
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: MockClient()))
    
    buffer_dir = tmp_path / "nested" / "mqtt"
    assert not buffer_dir.exists()
    
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=buffer_dir)
    
    assert buffer_dir.exists()
    assert buffer_dir.is_dir()
