# M3 Milestone Completion Summary

## Milestone: Capture pipeline + band-scan + logging + MQTT publisher + on-disk buffering

### Completed Features

#### 1. MQTT Publisher with On-Disk Buffering
- **Location**: `src/neo_igate/telemetry/mqtt_publisher.py`
- **Features**:
  - Persistent message buffering when broker is unavailable
  - Automatic buffer drainage on connection establishment
  - Configurable buffer directory (defaults to XDG_STATE_HOME)
  - Configurable maximum buffer size with automatic rotation
  - Exponential backoff for connection retries
  - Comprehensive error handling and logging

#### 2. Buffer Management
- Messages are stored as JSON-lines in `mqtt_buffer.jsonl`
- When buffer reaches capacity, oldest messages are automatically dropped
- Failed messages during drain are re-buffered for later retry
- Buffer is cleared automatically when all messages successfully send

#### 3. Configuration Options
- `buffer_dir`: Optional Path to buffer directory (auto-creates if needed)
- `max_buffer_size`: Maximum number of messages to buffer (default: 10,000)
- Inherits existing reconnection parameters (max_retries, backoff timings)

#### 4. Test Coverage
New test file: `tests/test_mqtt_buffer.py`
- `test_buffer_message_when_not_connected`: Verifies messages buffer when disconnected
- `test_drain_buffer_on_connect`: Verifies buffer drains on successful connection
- `test_buffer_rotation_at_capacity`: Verifies oldest messages dropped at capacity
- `test_partial_drain_on_publish_failure`: Verifies failed messages remain buffered
- `test_buffer_dir_creation`: Verifies buffer directory auto-creation

All existing tests continue to pass (158 tests total).

### Integration with WSPR Module
- WSPR capture pipeline uses `wspr/publisher.py` factory
- Factory creates MqttPublisher with appropriate configuration
- WSPR spots are automatically buffered if broker unavailable
- Spots are published to `neo_igate/wspr/spots` topic

### Documentation Updates
- Updated `docs/wspr.md` with buffer feature description
- Marked M3 milestone as complete (✓)

### Technical Details

#### Buffer File Format
```jsonl
{"topic": "neo_igate/wspr/spots", "body": "{\"call\":\"K1ABC\",\"freq\":14097100,...}", "ts": 1234567890.123}
```

#### Buffer Lifecycle
1. Message fails to publish → buffered to disk
2. Connection established → `_on_connect` triggered
3. Buffer automatically drained in order
4. Successful publishes removed from buffer
5. Failed publishes remain for next drain attempt

#### Error Handling
- All buffer I/O errors are logged but don't crash the publisher
- Individual publish failures during drain are caught and re-buffered
- Outer exception handler prevents drain errors from affecting main flow

### Next Steps (M4)
- Diagnostics tools for upconverter detection
- PPM calibration utilities
- WWV/CHU beacon testing

---
**Status**: M3 Complete ✓
**Test Results**: 158/158 passing
**Date**: 2025-11-09
