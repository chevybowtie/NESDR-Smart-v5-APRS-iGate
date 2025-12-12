import sys
import types
from types import SimpleNamespace


def test_make_publisher_disabled():
    from neo_wspr.wspr.publisher import make_publisher_from_config

    cfg = SimpleNamespace(mqtt_enabled=False)
    assert make_publisher_from_config(cfg) is None


def test_make_publisher_enabled_defaults(monkeypatch):
    mod = types.ModuleType("neo_telemetry.mqtt_publisher")
    captured = {}

    class FakePub:
        def __init__(self, host=None, port=None):
            captured["host"] = host
            captured["port"] = port

    mod.MqttPublisher = FakePub
    monkeypatch.setitem(sys.modules, "neo_telemetry.mqtt_publisher", mod)

    from neo_wspr.wspr.publisher import make_publisher_from_config

    cfg = SimpleNamespace(mqtt_enabled=True, mqtt_host=None, mqtt_port=None)
    pub = make_publisher_from_config(cfg)
    assert isinstance(pub, FakePub)
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 1883


def test_make_publisher_enabled_custom_port_str(monkeypatch):
    mod = types.ModuleType("neo_telemetry.mqtt_publisher")
    captured = {}

    class FakePub:
        def __init__(self, host=None, port=None):
            captured["host"] = host
            captured["port"] = port

    mod.MqttPublisher = FakePub
    monkeypatch.setitem(sys.modules, "neo_telemetry.mqtt_publisher", mod)

    from neo_wspr.wspr.publisher import make_publisher_from_config

    cfg = SimpleNamespace(mqtt_enabled=True, mqtt_host="1.2.3.4", mqtt_port="1234")
    pub = make_publisher_from_config(cfg)
    assert isinstance(pub, FakePub)
    assert captured["host"] == "1.2.3.4"
    assert captured["port"] == 1234
