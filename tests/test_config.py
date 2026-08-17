from __future__ import annotations

import json
from pathlib import Path

import pytest

from vellum.config import InputDevice, Settings, SettingsError, SettingsStore, VellumPaths


def test_vocabulary_hints_include_vellum_and_configured_domain_terms(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VELLUM_VOCABULARY_HINTS", "CTranslate2,  Acme API  ,")

    paths = VellumPaths.from_environment()

    assert paths.vocabulary_hints == ("Vellum", "CTranslate2", "Acme API")


def test_settings_round_trip_all_persisted_preferences(tmp_path: Path) -> None:
    settings_file = tmp_path / "Vellum" / "settings.json"
    store = SettingsStore(settings_file)
    settings = Settings(
        input_device=InputDevice("USB Microphone", "Windows WASAPI"),
        activation_hotkey="shift+control+d",
        sounds_enabled=False,
        start_at_sign_in=True,
    )

    store.save(settings)

    assert store.load() == Settings(
        input_device=InputDevice("USB Microphone", "Windows WASAPI"),
        activation_hotkey="Ctrl+Shift+D",
        sounds_enabled=False,
        start_at_sign_in=True,
    )
    assert json.loads(settings_file.read_text(encoding="utf-8")) == {
        "version": 1,
        "input_device": {"name": "USB Microphone", "host_api": "Windows WASAPI"},
        "activation_hotkey": "Ctrl+Shift+D",
        "sounds_enabled": False,
        "start_at_sign_in": True,
    }
    assert list(settings_file.parent.glob("*.tmp")) == []


def test_missing_settings_use_safe_defaults(tmp_path: Path) -> None:
    assert SettingsStore(tmp_path / "settings.json").load() == Settings()


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
