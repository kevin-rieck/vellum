"""Filesystem locations and persisted user settings for Vellum."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vellum.transcription_engines import (
    LARGE_V3_TURBO,
    TranscriptionEngineId,
    transcription_engine_by_id,
)

_SETTINGS_VERSION = 3
_PREVIOUS_SETTINGS_VERSION = 2
_LEGACY_SETTINGS_VERSION = 1
_MODIFIER_ORDER = ("Ctrl", "Alt", "Shift", "Win")
_MODIFIER_ALIASES = {
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Win",
    "windows": "Win",
    "cmd": "Win",
    "command": "Win",
}
_NAMED_ACTIVATION_KEYS = {
    "Space",
    "Enter",
    "Tab",
    "Esc",
    *{f"F{number}" for number in range(1, 25)},
}


class SettingsError(ValueError):
    """Raised when persisted Settings cannot be safely used."""


def normalise_activation_hotkey(value: str) -> str:
    """Return a supported Activation hotkey in its canonical display form.

    Vellum deliberately supports a constrained set rather than trying to execute
    arbitrary key descriptions stored in its user-owned settings file.
    """
    if not isinstance(value, str):
        raise SettingsError("The Activation hotkey must be text.")

    parts = [part.strip() for part in value.split("+")]
    if len(parts) < 2 or any(not part for part in parts):
        raise SettingsError("Use an Activation hotkey such as Ctrl+Alt+Space.")

    modifiers: set[str] = set()
    activation_key: str | None = None
    for index, part in enumerate(parts):
        modifier = _MODIFIER_ALIASES.get(part.casefold())
        if modifier is not None:
            if activation_key is not None:
                raise SettingsError("Modifiers must appear before the Activation key.")
            if modifier in modifiers:
                raise SettingsError(f"The Activation hotkey repeats {modifier}.")
            modifiers.add(modifier)
            continue

        if index != len(parts) - 1 or activation_key is not None:
            raise SettingsError("Use one non-modifier Activation key.")
        activation_key = _normalise_activation_key(part)

    if not modifiers or activation_key is None:
        raise SettingsError("Use at least one modifier and one Activation key.")
    ordered_modifiers = [modifier for modifier in _MODIFIER_ORDER if modifier in modifiers]
    return "+".join((*ordered_modifiers, activation_key))


def normalise_vocabulary_hints(value: Sequence[str]) -> tuple[str, ...]:
    """Return distinct user-provided Vocabulary hints in their entered order."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise SettingsError("Vocabulary hints must be a list of text terms.")

    seen: set[str] = set()
    hints: list[str] = []
    for hint in value:
        if not isinstance(hint, str):
            raise SettingsError("Vocabulary hints must contain only text terms.")
        normalised_hint = hint.strip()
        if not normalised_hint:
            continue
        key = normalised_hint.casefold()
        if key not in seen:
            seen.add(key)
            hints.append(normalised_hint)
    return tuple(hints)


def _normalise_activation_key(value: str) -> str:
    if len(value) == 1 and value.isascii() and (value.isalpha() or value.isdigit()):
        return value.upper()

    named_key = next(
        (
            candidate
            for candidate in _NAMED_ACTIVATION_KEYS
            if candidate.casefold() == value.casefold()
        ),
        None,
    )
    if named_key is not None:
        return named_key
    raise SettingsError(
        "The Activation key must be a letter, number, Space, Enter, Tab, Esc, or F1 through F24."
    )


@dataclass(frozen=True, slots=True)
class InputDevice:
    """A stable description of a user-selected microphone.

    Device indexes are intentionally not persisted: PortAudio may assign an index
    to a different microphone after devices are connected or removed.
    """

    name: str
    host_api: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise SettingsError("An Input device must have a name.")
        if not isinstance(self.host_api, str) or not self.host_api.strip():
            raise SettingsError("An Input device must have a host API.")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "host_api", self.host_api.strip())

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.host_api})"


def unambiguous_input_devices(devices: Sequence[InputDevice]) -> tuple[InputDevice, ...]:
    """Return Input devices that have exactly one stable description."""
    device_counts = Counter(devices)
    return tuple(device for device in devices if device_counts[device] == 1)


@dataclass(frozen=True, slots=True)
class Settings:
    """The user preferences required for the Vellum Tray application."""

    input_device: InputDevice | None = None
    activation_hotkey: str = "Ctrl+Alt+Space"
    sounds_enabled: bool = True
    start_at_sign_in: bool = False
    transcription_engine_id: TranscriptionEngineId = LARGE_V3_TURBO.id
    vocabulary_hints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.input_device is not None and not isinstance(self.input_device, InputDevice):
            raise SettingsError(
                "The Input device must be a saved Vellum device or Windows default."
            )
        object.__setattr__(
            self, "activation_hotkey", normalise_activation_hotkey(self.activation_hotkey)
        )
        if not isinstance(self.sounds_enabled, bool):
            raise SettingsError("The sounds preference must be true or false.")
        if not isinstance(self.start_at_sign_in, bool):
            raise SettingsError("The start-at-sign-in preference must be true or false.")
        if isinstance(self.transcription_engine_id, str):
            try:
                engine_id = TranscriptionEngineId(self.transcription_engine_id)
            except ValueError as error:
                raise SettingsError("The selected Transcription engine must be text.") from error
            object.__setattr__(self, "transcription_engine_id", engine_id)
        if not isinstance(self.transcription_engine_id, TranscriptionEngineId):
            raise SettingsError("The selected Transcription engine must be identified by an ID.")
        try:
            transcription_engine_by_id(self.transcription_engine_id)
        except (TypeError, ValueError) as error:
            raise SettingsError(
                f"The selected Transcription engine is not supported: "
                f"{str(self.transcription_engine_id)!r}."
            ) from error
        object.__setattr__(
            self, "vocabulary_hints", normalise_vocabulary_hints(self.vocabulary_hints)
        )

    @property
    def transcription_vocabulary_hints(self) -> tuple[str, ...]:
        """Return the mandatory product name plus the user's persisted technical terms."""
        return normalise_vocabulary_hints(("Vellum", *self.vocabulary_hints))

    def to_json(self) -> dict[str, object]:
        return {
            "version": _SETTINGS_VERSION,
            "input_device": (
                None
                if self.input_device is None
                else {"name": self.input_device.name, "host_api": self.input_device.host_api}
            ),
            "activation_hotkey": self.activation_hotkey,
            "sounds_enabled": self.sounds_enabled,
            "start_at_sign_in": self.start_at_sign_in,
            "engine_id": str(self.transcription_engine_id),
            "vocabulary_hints": list(self.vocabulary_hints),
        }

    @classmethod
    def from_json(cls, value: object) -> Settings:
        if not isinstance(value, dict):
            raise SettingsError("Settings must be a JSON object.")
        version = value.get("version")
        if version not in (_LEGACY_SETTINGS_VERSION, _PREVIOUS_SETTINGS_VERSION, _SETTINGS_VERSION):
            raise SettingsError("Settings use an unsupported version.")

        input_device_value = value.get("input_device")
        input_device: InputDevice | None
        if input_device_value is None:
            input_device = None
        elif isinstance(input_device_value, dict):
            input_device = InputDevice(
                name=_required_string(input_device_value, "name", "Input device"),
                host_api=_required_string(input_device_value, "host_api", "Input device"),
            )
        else:
            raise SettingsError("The Input device must be an object or null.")

        engine_id = str(LARGE_V3_TURBO.id)
        vocabulary_hints: tuple[str, ...] = ()
        if version == _PREVIOUS_SETTINGS_VERSION:
            engine_id = _required_string(value, "model_id", "Settings")
            vocabulary_hints = _required_vocabulary_hints(value)
        elif version == _SETTINGS_VERSION:
            engine_id = _required_string(value, "engine_id", "Settings")
            vocabulary_hints = _required_vocabulary_hints(value)

        return cls(
            input_device=input_device,
            activation_hotkey=_required_string(value, "activation_hotkey", "Settings"),
            sounds_enabled=_required_bool(value, "sounds_enabled"),
            start_at_sign_in=_required_bool(value, "start_at_sign_in"),
            transcription_engine_id=TranscriptionEngineId(engine_id),
            vocabulary_hints=vocabulary_hints,
        )


def _required_string(value: dict[str, Any], key: str, owner: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise SettingsError(f"{owner} {key.replace('_', ' ')} must be text.")
    return item


def _required_vocabulary_hints(value: dict[str, Any]) -> tuple[str, ...]:
    hints = value.get("vocabulary_hints")
    if not isinstance(hints, list):
        raise SettingsError("Settings vocabulary hints must be a list of text terms.")
    return normalise_vocabulary_hints(hints)


def _required_bool(value: dict[str, Any], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise SettingsError(f"Settings {key.replace('_', ' ')} must be true or false.")
    return item


class SettingsStore:
    """Reads and atomically writes the user-owned Vellum Settings file."""

    def __init__(self, settings_file: Path) -> None:
        self._settings_file = settings_file

    @property
    def settings_file(self) -> Path:
        return self._settings_file

    def load(self) -> Settings:
        if not self._settings_file.is_file():
            return Settings()
        try:
            contents = self._settings_file.read_text(encoding="utf-8")
            return Settings.from_json(json.loads(contents))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, SettingsError) as error:
            raise SettingsError(
                f"Vellum could not use Settings at {self._settings_file}: {error}"
            ) from error

    def save(self, settings: Settings) -> None:
        if not isinstance(settings, Settings):
            raise TypeError("Only Vellum Settings can be saved.")
        temporary_file: Path | None = None
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{self._settings_file.name}.",
                suffix=".tmp",
                dir=self._settings_file.parent,
                text=True,
            )
            temporary_file = Path(temporary_path)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                json.dump(settings.to_json(), file, indent=2, sort_keys=True)
                file.write("\n")
            os.replace(temporary_file, self._settings_file)
        except OSError as error:
            raise SettingsError(
                f"Vellum could not save Settings at {self._settings_file}: {error}"
            ) from error
        finally:
            if temporary_file is not None:
                try:
                    temporary_file.unlink(missing_ok=True)
                except OSError:
                    pass


@dataclass(frozen=True)
class VellumPaths:
    """Locations owned by Vellum; no Dictation session data is persisted here."""

    engine_directory: Path
    application_directory: Path

    @property
    def diagnostics_log_file(self) -> Path:
        """The local error log; it never contains audio or Transcripts."""
        return self.application_directory / "vellum.log"

    @property
    def settings_file(self) -> Path:
        """The user-owned file containing Vellum preferences, not session data."""
        return self.application_directory / "settings.json"

    @classmethod
    def from_environment(cls) -> VellumPaths:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        application_directory = local_app_data / "Vellum"
        configured_engine = os.environ.get("VELLUM_ENGINE_DIR")
        if configured_engine:
            return cls(
                engine_directory=Path(configured_engine).expanduser(),
                application_directory=application_directory,
            )

        return cls(
            engine_directory=application_directory / "engines" / "large-v3-turbo",
            application_directory=application_directory,
        )
