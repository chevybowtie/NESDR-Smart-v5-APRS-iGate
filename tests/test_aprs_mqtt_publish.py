from types import SimpleNamespace

from neo_aprs.commands.listen import _maybe_publish_mqtt


class DummyPublisher:
    def __init__(self):
        self.published = []
        self.topic = "neo_rx/aprs/messages"

    def publish(self, topic, payload):
        self.published.append((topic, payload))

    def connect(self):
        pass

    def disconnect(self):
        pass


def test_publish_message_frame():
    publisher = DummyPublisher()
    station_cfg = SimpleNamespace(mqtt_topic=None)
    # Typical APRS message TNC2: SRC>DST::RECIPIENT:Hello world
    tnc2 = "N0CALL>APRS::DEST:Hello MQTT"
    _maybe_publish_mqtt(publisher, station_cfg, tnc2)
    assert len(publisher.published) == 1
    topic, payload = publisher.published[0]
    assert topic == "neo_rx/aprs/messages"
    assert payload["callsign"] == "N0CALL"
    assert payload["message"] == "Hello MQTT"


def test_skip_position_report():
    publisher = DummyPublisher()
    station_cfg = SimpleNamespace(mqtt_topic=None)
    # Position report starts with ! or = or / or @ in INFO portion
    tnc2 = "N0CALL>APRS:!4903.50N/07201.75W-Test"
    _maybe_publish_mqtt(publisher, station_cfg, tnc2)
    assert len(publisher.published) == 0
