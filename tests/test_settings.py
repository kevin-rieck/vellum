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
