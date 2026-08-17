from __future__ import annotations

import json
from pathlib import Path

import pytest

from vellum.config import InputDevice, Settings, SettingsError, SettingsStore


def test_settings_round_trip_all_persisted_preferences(tmp_path: Path) -> None:
    settings_file = tmp_path / "Vellum" / "settings.json"
    store = SettingsStore(settings_file)
    settings = Settings(
        input_device=InputDevice("USB Microphone", "Windows WASAPI"),
        activation_hotkey="shift+control+d",
        transcription_model="large-v3-turbo",
        vocabulary_hints=("Vellum", "CTranslate2", "CUDA", "Acme API"),
        sounds_enabled=False,
        start_at_sign_in=True,
    )

    store.save(settings)

    assert store.load() == Settings(
        input_device=InputDevice("USB Microphone", "Windows WASAPI"),
        activation_hotkey="Ctrl+Shift+D",
        transcription_model="large-v3-turbo",
        vocabulary_hints=("Vellum", "CTranslate2", "CUDA", "Acme API"),
        sounds_enabled=False,
        start_at_sign_in=True,
    )
    assert json.loads(settings_file.read_text(encoding="utf-8")) == {
        "version": 2,
        "input_device": {"name": "USB Microphone", "host_api": "Windows WASAPI"},
        "activation_hotkey": "Ctrl+Shift+D",
        "transcription_model": "large-v3-turbo",
        "vocabulary_hints": ["Vellum", "CTranslate2", "CUDA", "Acme API"],
        "sounds_enabled": False,
        "start_at_sign_in": True,
    }
    assert list(settings_file.parent.glob("*.tmp")) == []


def test_missing_settings_use_safe_defaults(tmp_path: Path) -> None:
    assert SettingsStore(tmp_path / "settings.json").load() == Settings()


def test_version_one_settings_gain_v1_model_and_vocabulary_defaults(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "version": 1,
                "input_device": None,
                "activation_hotkey": "Ctrl+Alt+Space",
                "sounds_enabled": True,
                "start_at_sign_in": False,
            }
        ),
        encoding="utf-8",
    )

    assert SettingsStore(settings_file).load() == Settings(
        transcription_model="large-v3-turbo",
        vocabulary_hints=("Vellum", "CTranslate2", "CUDA", "Python", "GitHub"),
    )


def test_corrupt_settings_are_reported_without_overwriting_the_file(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{not JSON", encoding="utf-8")

    with pytest.raises(SettingsError, match="could not use Settings"):
        SettingsStore(settings_file).load()

    assert settings_file.read_text(encoding="utf-8") == "{not JSON"


@pytest.mark.parametrize("hotkey", ["Space", "Ctrl+Alt", "Ctrl+Ctrl+P", "Ctrl+Alt+F25"])
def test_settings_reject_unsafe_or_incomplete_activation_hotkeys(hotkey: str) -> None:
    with pytest.raises(SettingsError):
        Settings(activation_hotkey=hotkey)


@pytest.mark.parametrize(
    ("transcription_model", "vocabulary_hints"),
    [
        ("small", ("Vellum",)),
        ("large-v3-turbo", ("Python", "python")),
        ("large-v3-turbo", ("",)),
    ],
)
def test_settings_reject_unsupported_models_and_unsafe_vocabulary_hints(
    transcription_model: str, vocabulary_hints: tuple[str, ...]
) -> None:
    with pytest.raises(SettingsError):
        Settings(
            transcription_model=transcription_model,
            vocabulary_hints=vocabulary_hints,
        )
