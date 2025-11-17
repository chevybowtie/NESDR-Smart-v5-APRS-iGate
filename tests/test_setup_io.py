from __future__ import annotations

from typing import Iterator

import pytest

from neo_rx.commands import setup_io
from neo_rx.config import StationConfig


def test_prompt_string_validates_and_transforms() -> None:
    responses = iter(["", "bad", "good"])
    echoes: list[str] = []

    def fake_input(_: str) -> str:
        return next(responses)

    def validator(value: str) -> None:
        if value != "GOOD":
            raise ValueError("Must be GOOD")

    prompt = setup_io.Prompt(
        None,
        input_func=fake_input,
        echo=lambda message: echoes.append(message),
    )

    result = prompt.string("Label", transform=str.upper, validator=validator)

    assert result == "GOOD"
    assert "Value required" in echoes[0]
    assert "Must be GOOD" in echoes[1]


def test_prompt_optional_string_returns_default() -> None:
    prompt = setup_io.Prompt(None, input_func=lambda _: "", echo=lambda _: None)
    assert prompt.optional_string("Label", default="existing") == "existing"


def test_prompt_integer_enforces_bounds() -> None:
    responses = iter(["abc", "3", "150"])
    echoes: list[str] = []

    prompt = setup_io.Prompt(
        None,
        input_func=lambda _: next(responses),
        echo=lambda message: echoes.append(message),
    )

    result = prompt.integer("Rate", minimum=10, maximum=200)

    assert result == 150
    assert "Enter a valid integer" in echoes[0]
    assert "Value must be >= 10" in echoes[1]


def test_prompt_optional_float_handles_invalid() -> None:
    responses = iter(["", "oops", "1.23"])
    echoes: list[str] = []

    prompt = setup_io.Prompt(
        None,
        input_func=lambda _: next(responses),
        echo=lambda message: echoes.append(message),
    )

    result = prompt.optional_float("Freq")

    assert result is None

    # Repeat to exercise invalid branch
    result2 = prompt.optional_float("Freq")
    assert result2 == pytest.approx(1.23)
    assert "Enter a numeric value" in echoes[0]


def test_prompt_secret_handles_defaults_and_mismatch() -> None:
    secrets = iter(["", "first", "second", "second", "second"])
    echoes: list[str] = []

    prompt = setup_io.Prompt(
        StationConfig(callsign="N0CALL", passcode="secret"),
        secret_func=lambda _: next(secrets),
        echo=lambda message: echoes.append(message),
    )

    kept = prompt.secret("Passcode", default="secret")
    assert kept == "secret"

    changed = prompt.secret("Passcode")
    assert changed == "second"
    assert "Passcodes do not match" in echoes[0]


def test_prompt_session_ask_yes_no_uses_injected_functions() -> None:
    responses = iter(["yes"])
    echoed: list[str] = []

    session = setup_io.PromptSession(
        None,
        input_func=lambda _: next(responses),
        echo=lambda message: echoed.append(message),
        secret_func=lambda _: "ignored",
    )

    assert session.ask_yes_no("Continue?", default=False) is True
    assert session.prompt is session.prompt  # cached instance reuse


def test_prompt_yes_no_invalid_then_default(monkeypatch, capsys) -> None:
    responses: Iterator[str] = iter(["maybe", ""])

    def fake_input(_: str) -> str:
        return next(responses)

    echo_messages: list[str] = []

    result = setup_io.prompt_yes_no(
        "Proceed?",
        default=True,
        input_func=fake_input,
        echo=lambda message: echo_messages.append(message),
    )

    assert result is True
    assert "Please answer" in echo_messages[0]


def test_format_prompt_and_parse_helpers() -> None:
    assert setup_io._format_prompt("Label", "default") == "Label [default]: "
    assert setup_io._format_prompt("Label", None) == "Label: "
    assert setup_io._parse_int("10") == 10
    assert setup_io._parse_int("oops") is None
    assert setup_io._parse_float("1.5") == pytest.approx(1.5)
    assert setup_io._parse_float("oops") is None
