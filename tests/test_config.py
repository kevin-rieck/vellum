from __future__ import annotations

import json
from pathlib import Path

import pytest

from vellum.config import InputDevice, Settings, SettingsError, SettingsStore
from vellum.transcription_engines import LARGE_V3_TURBO, TranscriptionEngineId


def test_settings_round_trip_all_persisted_preferences(tmp_path: Path) -> None:
    settings_file = tmp_path / "Vellum" / "settings.json"
    store = SettingsStore(settings_file)
    settings = Settings(
        input_device=InputDevice("USB Microphone", "Windows WASAPI"),
        activation_hotkey="shift+control+d",
        sounds_enabled=False,
        start_at_sign_in=True,
        vocabulary_hints=("CTranslate2", "Acme API"),
    )

    store.save(settings)

    assert store.load() == Settings(
        input_device=InputDevice("USB Microphone", "Windows WASAPI"),
        activation_hotkey="Ctrl+Shift+D",
        sounds_enabled=False,
        start_at_sign_in=True,
        vocabulary_hints=("CTranslate2", "Acme API"),
    )
    assert json.loads(settings_file.read_text(encoding="utf-8")) == {
        "version": 3,
        "input_device": {"name": "USB Microphone", "host_api": "Windows WASAPI"},
        "activation_hotkey": "Ctrl+Shift+D",
        "sounds_enabled": False,
        "start_at_sign_in": True,
        "engine_id": "large-v3-turbo",
        "vocabulary_hints": ["CTranslate2", "Acme API"],
    }
    assert list(settings_file.parent.glob("*.tmp")) == []


def test_settings_wraps_the_transcription_engine_identifier() -> None:
    settings = Settings(transcription_engine_id="large-v3-turbo")

    assert settings.transcription_engine_id == LARGE_V3_TURBO.id
    assert isinstance(settings.transcription_engine_id, TranscriptionEngineId)


def test_missing_settings_use_safe_defaults(tmp_path: Path) -> None:
    assert SettingsStore(tmp_path / "settings.json").load() == Settings()


def test_persisted_vocabulary_hints_include_vellum_once_for_the_transcription_engine() -> None:
    settings = Settings(vocabulary_hints=("CTranslate2", "Vellum", "ctranslate2", "Acme API"))

    assert settings.vocabulary_hints == ("CTranslate2", "Vellum", "Acme API")
    assert settings.transcription_vocabulary_hints == ("Vellum", "CTranslate2", "Acme API")


def test_version_1_settings_migrate_to_the_default_engine_and_no_vocabulary_hints(
    tmp_path: Path,
) -> None:
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

    assert SettingsStore(settings_file).load() == Settings()


def test_version_2_settings_migrate_to_the_engine_identifier(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "version": 2,
                "input_device": None,
                "activation_hotkey": "Ctrl+Alt+Space",
                "sounds_enabled": True,
                "start_at_sign_in": False,
                "model_id": "large-v3-turbo",
                "vocabulary_hints": ["CTranslate2"],
            }
        ),
        encoding="utf-8",
    )

    assert SettingsStore(settings_file).load() == Settings(vocabulary_hints=("CTranslate2",))


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
