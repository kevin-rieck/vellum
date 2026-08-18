from __future__ import annotations

from pathlib import Path

import pytest

from vellum.config import Settings, SettingsStore
from vellum.settings import SettingsController


class FakeStartAtSignIn:
    def __init__(self) -> None:
        self.preferences: list[bool] = []

    def set_enabled(self, enabled: bool) -> None:
        self.preferences.append(enabled)


def test_settings_controller_persists_and_applies_a_saved_preference_set(tmp_path: Path) -> None:
    start_at_sign_in = FakeStartAtSignIn()
    applied: list[Settings] = []
    store = SettingsStore(tmp_path / "settings.json")
    controller = SettingsController(store, start_at_sign_in, applied.append)
    settings = Settings(
        activation_hotkey="Ctrl+Shift+D", sounds_enabled=False, start_at_sign_in=True
    )

    controller.save(settings)

    assert store.load() == settings
    assert start_at_sign_in.preferences == [True]
    assert applied == [settings]


def test_settings_controller_does_not_persist_or_enable_start_at_sign_in_when_runtime_apply_fails(
    tmp_path: Path,
) -> None:
    previous_settings = Settings(sounds_enabled=False)
    updated_settings = Settings(sounds_enabled=False, start_at_sign_in=True)
    store = SettingsStore(tmp_path / "settings.json")
    store.save(previous_settings)
    start_at_sign_in = FakeStartAtSignIn()

    def reject_runtime_settings(_: Settings) -> None:
        raise RuntimeError("Input device is unavailable.")

    controller = SettingsController(
        store,
        start_at_sign_in,
        reject_runtime_settings,
    )

    with pytest.raises(RuntimeError, match="Input device is unavailable"):
        controller.save(updated_settings)

    assert store.load() == previous_settings
    assert start_at_sign_in.preferences == []


def test_settings_controller_does_not_persist_when_start_at_sign_in_apply_fails(
    tmp_path: Path,
) -> None:
    class FailingStartAtSignIn:
        def set_enabled(self, _: bool) -> None:
            raise RuntimeError("Windows refused the start-at-sign-in preference.")

    previous_settings = Settings(sounds_enabled=False)
    updated_settings = Settings(sounds_enabled=False, start_at_sign_in=True)
    store = SettingsStore(tmp_path / "settings.json")
    store.save(previous_settings)
    applied: list[Settings] = []
    controller = SettingsController(store, FailingStartAtSignIn(), applied.append)

    with pytest.raises(RuntimeError, match="Windows refused"):
        controller.save(updated_settings)

    assert store.load() == previous_settings
    assert applied == [updated_settings, previous_settings]


def test_settings_controller_restores_applied_settings_when_persistence_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    previous_settings = Settings(sounds_enabled=False)
    updated_settings = Settings(sounds_enabled=False, start_at_sign_in=True)
    store = SettingsStore(tmp_path / "settings.json")
    store.save(previous_settings)
    start_at_sign_in = FakeStartAtSignIn()
    applied: list[Settings] = []
    controller = SettingsController(store, start_at_sign_in, applied.append)

    def reject_persistence(_: Settings) -> None:
        raise RuntimeError("Vellum could not save Settings.")

    monkeypatch.setattr(store, "save", reject_persistence)

    with pytest.raises(RuntimeError, match="could not save Settings"):
        controller.save(updated_settings)

    assert applied == [updated_settings, previous_settings]
    assert start_at_sign_in.preferences == [True, False]


def test_settings_controller_checks_runtime_state_before_persisting_or_changing_startup(
    tmp_path: Path,
) -> None:
    start_at_sign_in = FakeStartAtSignIn()

    def reject_while_active(_: Settings) -> None:
        raise RuntimeError("Release Push-to-talk before saving Settings.")

    store = SettingsStore(tmp_path / "settings.json")
    controller = SettingsController(store, start_at_sign_in, lambda _: None, reject_while_active)

    with pytest.raises(RuntimeError, match="Release Push-to-talk"):
        controller.save(Settings(start_at_sign_in=True))

    assert store.load() == Settings()
    assert start_at_sign_in.preferences == []
