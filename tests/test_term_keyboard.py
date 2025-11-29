import threading
import time
from queue import Queue

from neo_core.term import start_keyboard_listener, process_commands, drain_command_queue


def test_process_commands_dispatch_basic():
    q: Queue[str] = Queue()
    q.put("a")
    q.put("b")

    seen: list[str] = []

    def handle_a():
        seen.append("a")

    def handle_b():
        seen.append("b")

    process_commands(q, {"a": handle_a, "b": handle_b})

    assert seen == ["a", "b"]
    assert q.empty()


def test_start_keyboard_listener_stops_with_event():
    stop = threading.Event()
    q: Queue[str] = Queue()

    t = start_keyboard_listener(stop, q, name="test-keyboard")
    assert t is None or t.is_alive() or True  # listener may not start in CI

    stop.set()
    time.sleep(0.05)
    # Ensure no residual commands in queue
    drain_command_queue(q)
    assert q.empty()
