from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from vellum.config import Settings, SettingsStore
from vellum.settings import SettingsController, SettingsWindow


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


def test_settings_window_saves_the_transcription_model_and_vocabulary_hints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWindow:
        def title(self, _: str) -> None:
            pass

        def resizable(self, _: bool, __: bool) -> None:
            pass

        def destroy(self) -> None:
            pass

        def mainloop(self) -> None:
            for editor in FakeText.editors:
                editor.value = "Kubernetes\nTerraform"
            next(button for button in FakeButton.buttons if button.text == "Save").command()

    class FakeVariable:
        def __init__(self, *, value: object) -> None:
            self.value = value

        def get(self) -> object:
            return self.value

    class FakeWidget:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def grid(self, **_: object) -> None:
            pass

    class FakeText(FakeWidget):
        editors: list[FakeText] = []

        def __init__(self, *_: object, **__: object) -> None:
            super().__init__()
            self.value = ""
            self.editors.append(self)

        def insert(self, _: str, value: str) -> None:
            self.value = value

        def get(self, _: str, __: str) -> str:
            return self.value

    class FakeCombobox(FakeWidget):
        instances: list[FakeCombobox] = []

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.values = kwargs["values"]
            self.instances.append(self)

    class FakeButton(FakeWidget):
        buttons: list[FakeButton] = []

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.text = kwargs["text"]
            command = kwargs["command"]
            assert callable(command)
            self.command = command
            self.buttons.append(self)

    fake_tk = SimpleNamespace(
        Tk=FakeWindow,
        StringVar=FakeVariable,
        BooleanVar=FakeVariable,
        Text=FakeText,
    )
    fake_ttk = SimpleNamespace(
        Frame=FakeWidget,
        Label=FakeWidget,
        Combobox=FakeCombobox,
        Entry=FakeWidget,
        Checkbutton=FakeWidget,
        Button=FakeButton,
    )
    monkeypatch.setitem(sys.modules, "tkinter", SimpleNamespace(**fake_tk.__dict__, ttk=fake_ttk))

    saved: list[Settings] = []
    SettingsWindow(Settings(), saved.append, input_devices=lambda: ()).show()

    assert saved == [Settings(vocabulary_hints=("Kubernetes", "Terraform"))]
    assert ("large-v3-turbo",) in [selector.values for selector in FakeCombobox.instances]


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
