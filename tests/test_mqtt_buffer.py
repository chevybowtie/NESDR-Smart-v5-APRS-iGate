"""Tests for MQTT publisher on-disk buffering."""
import json
import types


import neo_rx.telemetry.mqtt_publisher as mp


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
    pub.publish("neo_rx/wspr/spots", {"call": "K1ABC"})
    
    queue_dir = tmp_path / "queue"
    files = list(queue_dir.glob("*.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text())
    assert record["topic"] == "neo_rx/wspr/spots"
    assert "K1ABC" in record["body"]


def test_drain_buffer_on_connect(monkeypatch, tmp_path):
    """When connection is established, buffered messages should be sent."""
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)
    
    # Create a queue with one message
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    msg_file = queue_dir / "0001-test.json"
    msg_file.write_text(json.dumps({"topic": "neo_rx/wspr/spots", "body": '{"call":"K1ABC"}', "ts": 1234567890}))
    
    mock = MockClient()
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: mock))
    
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    pub.connect()
    
    # Queue should be drained and file should be removed
    files = list(queue_dir.glob("*.json"))
    assert not files
    assert len(mock._publish_calls) == 1
    assert mock._publish_calls[0][0] == "neo_rx/wspr/spots"


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
        pub.publish("neo_rx/test", {"msg": i})
    
    queue_dir = tmp_path / "queue"
    files = sorted(queue_dir.glob("*.json"))

    # Should only have 3 messages (last 3)
    assert len(files) == 3

    # Verify we kept the newest messages
    records = [json.loads(p.read_text()) for p in files]
    msgs = [json.loads(r["body"])['msg'] for r in records]
    assert msgs == [2, 3, 4]


def test_partial_drain_on_publish_failure(monkeypatch, tmp_path):
    """If some buffered messages fail to publish, they should remain in buffer."""
    monkeypatch.setattr(mp.time, "sleep", lambda x: None)
    
    # Create queue with 3 messages
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        f = queue_dir / f"msg-{i:03d}.json"
        f.write_text(json.dumps({"topic": f"neo_rx/test/{i}", "body": f'{{"msg":{i}}}', "ts": 1234567890 + i}))
    
    # Mock client that fails on 2nd and 3rd publish
    behavior = {"publish_fail_times": 2}
    mock = MockClient(behavior=behavior)
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: mock))
    
    pub = mp.MqttPublisher(host="fake", port=1883, buffer_dir=tmp_path)
    pub.connect()
    
    # Queue should still contain the failed messages
    files = sorted((tmp_path / "queue").glob("*.json"))
    # First message succeeded, 2nd and 3rd failed, so we should have 2 remaining
    assert len(files) == 2


def test_buffer_dir_creation(monkeypatch, tmp_path):
    """Buffer directory should be created if it doesn't exist."""
    monkeypatch.setattr(mp, "mqtt", types.SimpleNamespace(Client=lambda: MockClient()))
    
    buffer_dir = tmp_path / "nested" / "mqtt"
    assert not buffer_dir.exists()
    
    mp.MqttPublisher(host="fake", port=1883, buffer_dir=buffer_dir)
    
    assert buffer_dir.exists()
    assert buffer_dir.is_dir()
