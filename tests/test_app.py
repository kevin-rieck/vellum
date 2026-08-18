from __future__ import annotations

from pathlib import Path

import pytest

from vellum import app
from vellum.config import Settings, VellumPaths
from vellum.startup import StartupPrerequisiteError


class PassingModelVerifier:
    def verify(self, *_: object) -> None:
        pass


def test_missing_model_keeps_the_tray_open_for_explicit_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = VellumPaths(tmp_path / "models" / "large-v3-turbo", tmp_path / "Vellum")
    events: list[str] = []

    class FakeSettingsStore:
        def __init__(self, _: Path) -> None:
            pass

        def load(self) -> Settings:
            return Settings()

    class FakeSettingsController:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def save(self, _: Settings) -> None:
            pass

    class FakeProbe:
        model_available = False
        cuda_available = True
        model_directory = paths.model_directory

    class FakeTray:
        def __init__(self, _: Settings) -> None:
            events.append("constructed")

        def set_settings_controller(self, _: object) -> None:
            events.append("settings")

        def set_model_onboarding(self, *_: object) -> None:
            events.append("onboarding")

        def model_setup_required(self) -> None:
            events.append("setup-required")

        def fail_startup(self, _: Exception) -> None:
            events.append("failed")

        def run(self, hotkey: object | None = None) -> bool:
            assert hotkey is None
            events.append("run")
            return True

    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app.VellumPaths, "from_environment", lambda: paths)
    monkeypatch.setattr(app, "configure_diagnostics", lambda _: None)
    monkeypatch.setattr(app, "SettingsStore", FakeSettingsStore)
    monkeypatch.setattr(app, "SettingsController", FakeSettingsController)
    monkeypatch.setattr(app, "TrayApplication", FakeTray)
    monkeypatch.setattr(app, "WindowsPrerequisiteProbe", lambda *_: FakeProbe())

    assert app.main() == 0
    assert events == ["constructed", "settings", "onboarding", "setup-required", "run"]


def test_startup_warms_the_selected_model_with_persisted_vocabulary_hints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = VellumPaths(tmp_path / "models" / "large-v3-turbo", tmp_path / "Vellum")
    warmed_with: list[tuple[Path, tuple[str, ...]]] = []
    updated_hints: list[tuple[str, ...]] = []

    class FakeSettingsStore:
        def __init__(self, _: Path) -> None:
            pass

        def load(self) -> Settings:
            return Settings(vocabulary_hints=("CTranslate2",))

    class FakeSettingsController:
        instance: FakeSettingsController | None = None

        def __init__(
            self, _: object, __: object, apply: object, *___: object, **____: object
        ) -> None:
            assert callable(apply)
            self._apply = apply
            FakeSettingsController.instance = self

        def save(self, settings: Settings) -> None:
            self._apply(settings)

        def sync_start_at_sign_in(self, _: Settings) -> None:
            pass

    class FakeEngine:
        def __init__(
            self, model_directory: Path, vocabulary_hints: tuple[str, ...], on_ready: object
        ) -> None:
            assert callable(on_ready)
            self._on_ready = on_ready
            warmed_with.append((model_directory, vocabulary_hints))

        def start_warming(self) -> None:
            self._on_ready(None)

        def set_vocabulary_hints(self, vocabulary_hints: tuple[str, ...]) -> None:
            updated_hints.append(vocabulary_hints)

    class FakeRecorder:
        def set_input_device(self, _: object) -> None:
            pass

    class FakeSession:
        active = False

        def __init__(self, **_: object) -> None:
            pass

    class FakeHotkey:
        def __init__(self, *_: object) -> None:
            self.enabled = False

        def enable(self) -> None:
            self.enabled = True

        def configure(self, _: str) -> None:
            pass

    class FakeTray:
        def __init__(self, _: Settings) -> None:
            pass

        def set_settings_controller(self, _: object) -> None:
            pass

        def set_model_onboarding(self, *_: object) -> None:
            pass

        def warming(self) -> None:
            pass

        def apply_settings(self, _: Settings) -> None:
            pass

        def feedback(self, _: object) -> None:
            pass

        def report_error(self, _: Exception) -> None:
            pass

        def run(self, hotkey: object | None = None) -> bool:
            assert isinstance(hotkey, FakeHotkey)
            assert hotkey.enabled is True
            assert FakeSettingsController.instance is not None
            FakeSettingsController.instance.save(Settings(vocabulary_hints=("CUDA",)))
            return True

    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app.VellumPaths, "from_environment", lambda: paths)
    monkeypatch.setattr(app, "configure_diagnostics", lambda _: None)
    monkeypatch.setattr(app, "SettingsStore", FakeSettingsStore)
    monkeypatch.setattr(app, "SettingsController", FakeSettingsController)
    monkeypatch.setattr(app, "TrayApplication", FakeTray)
    monkeypatch.setattr(app, "WindowsPrerequisiteProbe", lambda *_: object())
    monkeypatch.setattr(app, "ModelVerifier", PassingModelVerifier)
    monkeypatch.setattr(app, "require_startup_prerequisites", lambda _: None)
    monkeypatch.setattr(app, "SoundDeviceRecorder", lambda **_: FakeRecorder())
    monkeypatch.setattr(app, "AsyncFasterWhisperTranscriptionEngine", FakeEngine)
    monkeypatch.setattr(app, "DictationSession", FakeSession)
    monkeypatch.setattr(app, "PushToTalkHotkey", FakeHotkey)

    assert app.main() == 0
    assert warmed_with == [(paths.model_directory, ("Vellum", "CTranslate2"))]
    assert updated_hints == [("Vellum", "CUDA")]


def test_prerequisite_failure_runs_the_tray_until_the_user_quits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = VellumPaths(tmp_path / "models" / "large-v3-turbo", tmp_path / "Vellum")
    events: list[str] = []

    class FakeSettingsStore:
        def __init__(self, _: Path) -> None:
            pass

        def load(self) -> Settings:
            return Settings()

    class FakeTray:
        def __init__(self, _: Settings) -> None:
            events.append("constructed")

        def set_settings_controller(self, _: object) -> None:
            pass

        def set_model_onboarding(self, *_: object) -> None:
            pass

        def fail_startup(self, _: Exception) -> None:
            events.append("failed")

        def run(self, hotkey: object | None = None) -> bool:
            assert hotkey is None
            events.append("run")
            return False

    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app.VellumPaths, "from_environment", lambda: paths)
    monkeypatch.setattr(app, "configure_diagnostics", lambda _: None)
    monkeypatch.setattr(app, "SettingsStore", FakeSettingsStore)
    monkeypatch.setattr(app, "TrayApplication", FakeTray)
    monkeypatch.setattr(app, "WindowsPrerequisiteProbe", lambda *_: object())
    monkeypatch.setattr(app, "ModelVerifier", PassingModelVerifier)

    def fail_prerequisites(_: object) -> None:
        raise StartupPrerequisiteError("CUDA unavailable")

    monkeypatch.setattr(app, "require_startup_prerequisites", fail_prerequisites)

    assert app.main() == 2
    assert events == ["constructed", "failed", "run"]
