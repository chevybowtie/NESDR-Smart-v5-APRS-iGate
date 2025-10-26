"""Runtime command implementation for the APRS iGate listener."""

from __future__ import annotations

import signal
import subprocess
import threading
import time
from argparse import Namespace
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from types import FrameType
from typing import Callable, Iterator, Optional

from nesdr_igate import config as config_module
from nesdr_igate.aprs.ax25 import AX25DecodeError, kiss_payload_to_tnc2  # type: ignore[import]
from nesdr_igate.aprs.aprsis_client import APRSISClient, APRSISClientError, APRSISConfig  # type: ignore[import]
from nesdr_igate.aprs.kiss_client import KISSClient, KISSClientConfig, KISSClientError  # type: ignore[import]
from nesdr_igate.config import StationConfig
from nesdr_igate.radio.capture import AudioCaptureError, RtlFmAudioCapture, RtlFmConfig  # type: ignore[import]

try:
    from importlib import metadata as importlib_metadata
except ImportError:  # pragma: no cover
    import importlib_metadata  # type: ignore[no-redef]

AUDIO_SAMPLE_RATE = 22_050
_AUDIO_CHUNK_BYTES = 4096
_SOFTWARE_NAME = "nesdr-igate"

try:
    _SOFTWARE_VERSION = importlib_metadata.version("nesdr-igate")
except importlib_metadata.PackageNotFoundError:  # pragma: no cover - dev install fallback
    _SOFTWARE_VERSION = "0.0.0"


@dataclass
class _APRSState:
    """Track APRS-IS connection state and retry counters."""

    enabled: bool
    config: Optional[APRSISConfig]
    retry_base: float = 2.0
    retry_delay: float = 2.0
    retry_max: float = 120.0
    next_retry: float = 0.0
    forwarded: int = 0
    failed: int = 0
    client: Optional[APRSISClient] = None

    def attempt_connect(self) -> None:
        """Try to establish an APRS-IS connection when eligible."""

        if not self.enabled or self.config is None or self.client is not None:
            return
        now = time.monotonic()
        if now < self.next_retry:
            return
        try:
            candidate = APRSISClient(self.config)
            candidate.connect()
            self.client = candidate
            self.retry_delay = self.retry_base
            self.next_retry = 0.0
            print(f"Connected to APRS-IS {self.config.host}:{self.config.port}")
        except APRSISClientError as exc:
            delay = self.retry_delay
            print(f"APRS-IS connection failed: {exc}; retrying in {int(delay)}s")
            self.next_retry = now + delay
            self.retry_delay = min(self.retry_delay * 2, self.retry_max)

    def send_packet(self, packet: str) -> None:
        """Publish a decoded packet, tracking failures."""

        if not self.enabled or self.client is None:
            return
        try:
            self.client.send_packet(packet)
            self.forwarded += 1
        except APRSISClientError as exc:
            self.failed += 1
            print(f"APRS-IS transmission error: {exc}; scheduling reconnect")
            self.client.close()
            self.client = None
            self.retry_delay = self.retry_base
            self.next_retry = 0.0

    def close(self) -> None:
        """Close any active APRS-IS connection."""

        if self.client is not None:
            self.client.close()
            self.client = None


def run_listen(args: Namespace) -> int:
    """Run the igate listening loop."""

    config_path = config_module.resolve_config_path(getattr(args, "config", None))
    try:
        station_config = config_module.load_config(config_path)
    except FileNotFoundError:
        print(f"Config not found at {config_path}; run `nesdr-igate setup` first.")
        return 1
    except ValueError as exc:
        print(f"Config invalid: {exc}")
        return 1

    direwolf_conf = _resolve_direwolf_config(config_path.parent)
    if direwolf_conf is None:
        print("Direwolf configuration missing; rerun setup to render direwolf.conf")
        return 1

    rtl_config = _build_rtl_config(station_config)
    aprs_state = _initialize_aprs_state(station_config, not getattr(args, "no_aprsis", False))

    audio_errors: "Queue[Exception]" = Queue()
    stop_event = threading.Event()
    exit_code = 0
    frame_count = 0

    client = KISSClient(
        KISSClientConfig(
            host=station_config.kiss_host,
            port=station_config.kiss_port,
            timeout=2.0,
        )
    )

    with ExitStack() as stack:
        stack.callback(client.close)
        stack.callback(aprs_state.close)

        capture = RtlFmAudioCapture(rtl_config)
        stack.callback(capture.stop)

        handler = _make_sigint_handler(stop_event)
        with _temporary_signal(signal.SIGINT, handler):
            try:
                print("Starting rtl_fm capture...")
                capture.start()
            except AudioCaptureError as exc:
                print(f"Audio capture failed: {exc}")
                return 1

            try:
                direwolf_proc = _launch_direwolf_process(direwolf_conf, rtl_config.sample_rate)
            except OSError as exc:
                print(f"Failed to start Direwolf: {exc}")
                return 1

            stack.callback(lambda proc=direwolf_proc: _terminate_process(proc))

            audio_thread = _start_audio_thread(capture, direwolf_proc, stop_event, audio_errors)
            stack.callback(lambda thread=audio_thread: _stop_audio_thread(thread, stop_event))

            if not _wait_for_kiss(client, attempts=10, delay=0.5):
                print(
                    f"Unable to connect to Direwolf KISS at {station_config.kiss_host}:{station_config.kiss_port}."
                )
                return 1

            print("Connected to Direwolf KISS port; awaiting frames...")

            exit_code, frame_count = _run_main_loop(
                client,
                aprs_state,
                stop_event,
                audio_errors,
                getattr(args, "once", False),
            )

    if exit_code == 0:
        if aprs_state.enabled:
            print(
                f"Frames processed: {frame_count} (APRS-IS ok={aprs_state.forwarded}, failed={aprs_state.failed})"
            )
        else:
            print(f"Frames processed: {frame_count}")
    return exit_code


@contextmanager
def _temporary_signal(signum: int, handler: Callable[[int, Optional[FrameType]], None]) -> Iterator[None]:
    """Temporarily install a signal handler, restoring the previous one afterwards."""

    previous = signal.getsignal(signum)
    signal.signal(signum, handler)
    try:
        yield
    finally:
        signal.signal(signum, previous)


def _make_sigint_handler(stop_event: threading.Event) -> Callable[[int, Optional[FrameType]], None]:
    """Return a SIGINT handler that signals shutdown via an event."""

    def _handle(signum: int, frame: Optional[FrameType]) -> None:  # pragma: no cover - signal plumbing
        stop_event.set()
        raise KeyboardInterrupt

    return _handle


def _build_rtl_config(station_config: StationConfig) -> RtlFmConfig:
    """Construct rtl_fm configuration from listener station settings."""

    return RtlFmConfig(
        frequency_hz=station_config.center_frequency_hz,
        sample_rate=AUDIO_SAMPLE_RATE,
        gain=station_config.gain,
        ppm=station_config.ppm_correction or 0,
        device_index=0,
    )


def _initialize_aprs_state(station_config: StationConfig, aprs_enabled: bool) -> _APRSState:
    """Create APRS-IS runtime state from configuration flags."""

    if not aprs_enabled:
        print("APRS-IS uplink disabled (receive-only mode)")
        return _APRSState(enabled=False, config=None)

    config = APRSISConfig(
        host=station_config.aprs_server,
        port=station_config.aprs_port,
        callsign=station_config.callsign,
        passcode=station_config.passcode,
        software_name=_SOFTWARE_NAME,
        software_version=_SOFTWARE_VERSION,
    )
    return _APRSState(enabled=True, config=config)


def _launch_direwolf_process(config_path: Path, sample_rate: int) -> subprocess.Popen[bytes]:
    """Spawn the Direwolf TNC process for decoding audio."""

    direwolf_cmd = [
        "direwolf",
        "-c",
        str(config_path),
        "-r",
        str(sample_rate),
        "-t",
        "0",
        "-",
    ]
    process = subprocess.Popen(
        direwolf_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"Direwolf launched (PID {process.pid})")
    return process


def _start_audio_thread(
    capture: RtlFmAudioCapture,
    process: subprocess.Popen[bytes],
    stop_event: threading.Event,
    error_queue: "Queue[Exception]",
) -> threading.Thread:
    """Start the background worker that feeds rtl_fm audio into Direwolf."""

    thread = threading.Thread(
        target=_pump_audio,
        args=(capture, process, stop_event, error_queue),
        name="rtl_fm_audio",
        daemon=True,
    )
    thread.start()
    return thread


def _stop_audio_thread(thread: threading.Thread, stop_event: threading.Event) -> None:
    """Stop the audio forwarding thread and wait briefly for it to exit."""

    stop_event.set()
    if thread.is_alive():
        thread.join(timeout=1)


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate the Direwolf process, ensuring stdin is closed first."""

    if process.stdin:
        try:
            process.stdin.close()
        except OSError:
            pass
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        process.kill()


def _pump_audio(
    capture: RtlFmAudioCapture,
    process: subprocess.Popen[bytes],
    stop_event: threading.Event,
    error_queue: "Queue[Exception]",
) -> None:
    """Continuously forward rtl_fm audio into Direwolf until shutdown."""

    try:
        while not stop_event.is_set():
            chunk = capture.read(_AUDIO_CHUNK_BYTES)
            if not chunk:
                continue
            if process.stdin is None:
                continue
            try:
                process.stdin.write(chunk)
                process.stdin.flush()
            except BrokenPipeError as exc:  # pragma: no cover - depends on direwolf exit timing
                error_queue.put(exc)
                break
    except Exception as exc:  # pragma: no cover - defensive
        error_queue.put(exc)


def _run_main_loop(
    client: KISSClient,
    aprs_state: _APRSState,
    stop_event: threading.Event,
    audio_errors: "Queue[Exception]",
    once: bool,
) -> tuple[int, int]:
    """Drive frame forwarding until shutdown, returning status and frame count."""

    frame_count = 0
    stats_interval = 60.0
    next_stats_report = time.monotonic() + stats_interval

    try:
        while True:
            aprs_state.attempt_connect()
            if stop_event.is_set():
                break
            try:
                frame = client.read_frame(timeout=1.0)
            except TimeoutError:
                _maybe_print_audio_error(audio_errors)
                if not once and time.monotonic() >= next_stats_report:
                    print(
                        f"[stats] frames={frame_count} aprs_ok={aprs_state.forwarded} aprs_fail={aprs_state.failed}"
                    )
                    next_stats_report = time.monotonic() + stats_interval
                continue
            except KISSClientError as exc:
                print(f"KISS client error: {exc}")
                stop_event.set()
                return 1, frame_count

            try:
                tnc2_packet = kiss_payload_to_tnc2(frame.payload)
            except AX25DecodeError as exc:
                print(f"Skipping undecodable frame: {exc}")
                continue

            frame_count += 1
            _display_frame(frame_count, frame.port, tnc2_packet)
            aprs_state.send_packet(tnc2_packet)

            if once:
                break

            _maybe_print_audio_error(audio_errors)

            if not once and time.monotonic() >= next_stats_report:
                print(
                    f"[stats] frames={frame_count} aprs_ok={aprs_state.forwarded} aprs_fail={aprs_state.failed}"
                )
                next_stats_report = time.monotonic() + stats_interval
    except KeyboardInterrupt:
        stop_event.set()
        print("Stopping listener...")
        return 0, frame_count

    stop_event.set()
    return 0, frame_count


def _maybe_print_audio_error(queue: "Queue[Exception]") -> None:
    """Emit the next queued audio pipeline exception, if any."""

    error = _next_audio_error(queue)
    if error is not None:
        print(f"Audio pipeline error: {error}")


def _next_audio_error(queue: "Queue[Exception]") -> Exception | None:
    """Return the next queued audio exception without blocking."""

    try:
        return queue.get_nowait()
    except Empty:
        return None


def _resolve_direwolf_config(config_dir: Path) -> Optional[Path]:
    """Return the best available direwolf.conf path for the listener."""

    candidate = config_dir / "direwolf.conf"
    if candidate.exists():
        return candidate
    default_path = config_module.get_config_dir() / "direwolf.conf"
    return default_path if default_path.exists() else None


def _wait_for_kiss(client: KISSClient, *, attempts: int, delay: float) -> bool:
    """Attempt to establish a KISS connection, retrying with delays."""

    for attempt in range(attempts):
        try:
            client.connect()
            return True
        except KISSClientError:
            time.sleep(delay)
    return False


def _display_frame(count: int, port: int, tnc2_line: str) -> None:
    """Print a formatted summary line for a decoded TNC2 packet."""

    snippet = tnc2_line
    if len(snippet) > 120:
        snippet = snippet[:117] + "…"
    print(f"[{count:06d}] port={port} {snippet}")
