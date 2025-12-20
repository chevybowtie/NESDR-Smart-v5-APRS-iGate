"""Terminal helpers for optional colorized output and keyboard input.

Migrated from neo_rx.term to neo_core.term.
"""

from __future__ import annotations

import os
import sys
import threading
from queue import Queue, Empty
from typing import Literal

ColorLevel = Literal["ok", "warning", "error", "info"]

_ANSI = {
    "reset": "\x1b[0m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "red": "\x1b[31m",
    "blue": "\x1b[34m",
}


def supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _color_wrap(text: str, code: str, enabled: bool) -> str:
    if not enabled or code not in _ANSI:
        return text
    return f"{_ANSI[code]}{text}{_ANSI['reset']}"


def status_label(level: ColorLevel, *, enabled: bool = True) -> str:
    normalized = level.lower()
    if normalized == "ok":
        return _color_wrap("[OK     ]", "green", enabled)
    if normalized == "warning":
        return _color_wrap("[WARNING]", "yellow", enabled)
    if normalized == "error":
        return _color_wrap("[ERROR  ]", "red", enabled)
    return _color_wrap("[INFO   ]", "blue", enabled)


def color_text(text: str, *, color: str = "blue", enabled: bool = True) -> str:
    return _color_wrap(text, color, enabled)


def start_keyboard_listener(
    stop_event: threading.Event,
    command_queue: Queue[str],
    *,
    name: str = "neo-rx-keyboard",
) -> threading.Thread | None:
    """Start a background thread that reads single keypress characters from stdin.

    Returns None if stdin is not a TTY, required modules are unavailable,
    or terminal setup fails. Otherwise returns the started thread.

    The worker thread runs until stop_event is set, reading keypresses with
    select() and pushing them to command_queue. Terminal settings are restored
    on thread exit.

    Args:
        stop_event: Signal to stop the listener thread.
        command_queue: Queue to receive single-character keypresses.
        name: Thread name for debugging.

    Returns:
        Started thread, or None if keyboard listening is not possible.
    """
    # Guard against test monkeypatching that removes Event.wait
    try:
        test_event = threading.Event()
        if not hasattr(test_event, "wait"):
            return None
    except Exception:
        return None

    if not sys.stdin.isatty():
        return None

    try:
        import select
        import termios
        import tty
    except ImportError:
        return None

    try:
        fd = sys.stdin.fileno()
    except (OSError, ValueError):
        return None

    try:
        old_settings = termios.tcgetattr(fd)
    except termios.error:
        return None

    try:
        tty.setcbreak(fd)
    except termios.error:
        return None

    def worker() -> None:
        try:
            while not stop_event.is_set():
                try:
                    readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                except (OSError, ValueError):
                    break
                if sys.stdin in readable:
                    try:
                        ch = sys.stdin.read(1)
                    except (OSError, ValueError):
                        break
                    if ch:
                        command_queue.put(ch)
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except termios.error:
                pass

    thread = threading.Thread(target=worker, name=name, daemon=True)
    thread.start()
    return thread


def drain_command_queue(queue: Queue[str]) -> list[str]:
    """Drain all pending commands from the queue without blocking.

    Returns:
        List of command strings (single characters).
    """
    commands = []
    while True:
        try:
            commands.append(queue.get_nowait())
        except Empty:
            break
    return commands


def process_commands(
    queue: Queue[str],
    handlers: dict[str, "callable"],
    *,
    default: "callable" | None = None,
) -> None:
    """Drain queue and dispatch to handlers by single-character key.

    Args:
        queue: Source of keypress strings.
        handlers: Mapping of lowercased keys to no-arg callables.
        default: Optional callable invoked when no handler exists for a key.
    """
    while True:
        try:
            cmd = queue.get_nowait()
        except Empty:
            break
        key = cmd.lower()
        fn = handlers.get(key)
        if fn is not None:
            try:
                fn()
            except Exception:
                # Swallow exceptions from handlers to avoid crashing the loop
                pass
        elif default is not None:
            try:
                default()
            except Exception:
                pass
