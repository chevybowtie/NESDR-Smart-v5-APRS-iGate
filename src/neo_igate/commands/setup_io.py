"""Interactive prompt helpers for the setup command."""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from getpass import getpass as default_getpass
from typing import Any, Callable

from neo_igate.config import StationConfig

InputFunc = Callable[[str], str]
SecretFunc = Callable[[str], str]
EchoFunc = Callable[[str], None]


def _default_echo(message: str) -> None:
    print(message)


class Prompt:
    """Utility helpers for prompting user input with validation."""

    def __init__(
        self,
        existing: StationConfig | None,
        *,
        input_func: InputFunc | None = None,
        echo: EchoFunc | None = None,
        secret_func: SecretFunc | None = None,
    ) -> None:
        self._existing = existing
        self._input = input_func or builtins.input
        self._echo = echo or _default_echo
        self._secret = secret_func or default_getpass

    def string(
        self,
        label: str,
        default: object | None = None,
        *,
        transform: Callable[[str], str] | None = None,
        validator: Callable[[str], None] | None = None,
    ) -> str:
        """Prompt user for a required string, applying optional transforms and validation."""

        while True:
            prompt = _format_prompt(label, default)
            raw = self._input(prompt).strip()
            if not raw and default is not None:
                value = str(default)
            else:
                value = raw
            if not value:
                self._echo("Value required")
                continue
            if transform is not None:
                value = transform(value)
            if validator is not None:
                try:
                    validator(value)
                except ValueError as exc:
                    self._echo(str(exc))
                    continue
            return value

    def optional_string(self, label: str, default: object | None = None) -> str | None:
        """Prompt for a string that may be left blank to keep or remove existing values."""

        prompt = _format_prompt(label, default)
        raw = self._input(prompt).strip()
        if not raw:
            return None if default is None else str(default)
        return raw

    def integer(
        self,
        label: str,
        default: object | None = None,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        """Prompt for an integer within optional bounds, re-asking on invalid input."""

        while True:
            prompt = _format_prompt(label, default)
            raw = self._input(prompt).strip()
            if not raw and default is not None:
                value = _parse_int(default)
            else:
                value = _parse_int(raw)
            if value is None:
                self._echo("Enter a valid integer")
                continue
            if minimum is not None and value < minimum:
                self._echo(f"Value must be >= {minimum}")
                continue
            if maximum is not None and value > maximum:
                self._echo(f"Value must be <= {maximum}")
                continue
            return value

    def optional_float(self, label: str, default: object | None = None) -> float | None:
        """Prompt for an optional float, treating blanks as None or existing default."""

        while True:
            prompt = _format_prompt(label, default)
            raw = self._input(prompt).strip()
            if not raw:
                return None if default is None else _parse_float(default)
            parsed = _parse_float(raw)
            if parsed is None:
                self._echo("Enter a numeric value or leave blank")
                continue
            return parsed

    def secret(self, label: str, default: object | None = None) -> str:
        """Prompt for a secret string with confirmation, defaulting when allowed."""

        while True:
            if default is not None:
                prompt = f"{label} [leave blank to keep existing]: "
            else:
                prompt = f"{label}: "
            value = self._secret(prompt)
            if not value and default is not None:
                return str(default)
            if not value:
                self._echo("Value required")
                continue
            confirm = self._secret("Confirm passcode: ")
            if value != confirm:
                self._echo("Passcodes do not match; try again")
                continue
            return value


def prompt_yes_no(
    message: str,
    *,
    default: bool,
    input_func: InputFunc | None = None,
    echo: EchoFunc | None = None,
) -> bool:
    """Prompt user for a yes/no response, re-asking on invalid input."""

    input_impl = input_func or builtins.input
    echo_impl = echo or _default_echo
    default_hint = "Y/n" if default else "y/N"
    while True:
        response = input_impl(f"{message} [{default_hint}]: ").strip().lower()
        if not response:
            return default
        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        echo_impl("Please answer 'y' or 'n'")


@dataclass
class PromptSession:
    """Bundle prompt helpers with injectable I/O functions."""

    existing: StationConfig | None
    input_func: InputFunc | None = None
    echo: EchoFunc | None = None
    secret_func: SecretFunc | None = None
    _prompt: Prompt | None = field(init=False, default=None)

    def _resolve_input(self) -> InputFunc:
        return self.input_func or builtins.input

    def _resolve_echo(self) -> EchoFunc:
        return self.echo or _default_echo

    def _resolve_secret(self) -> SecretFunc:
        return self.secret_func or default_getpass

    @property
    def prompt(self) -> Prompt:
        if self._prompt is None:
            self._prompt = Prompt(
                self.existing,
                input_func=self._resolve_input(),
                echo=self._resolve_echo(),
                secret_func=self._resolve_secret(),
            )
        return self._prompt

    def ask_yes_no(self, message: str, *, default: bool) -> bool:
        return prompt_yes_no(
            message,
            default=default,
            input_func=self._resolve_input(),
            echo=self._resolve_echo(),
        )


def _format_prompt(label: str, default: object | None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    return f"{label}{suffix}: "


def _parse_int(raw: Any) -> int | None:
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_float(raw: Any) -> float | None:
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


__all__ = ["PromptSession", "prompt_yes_no"]
