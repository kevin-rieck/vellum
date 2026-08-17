from __future__ import annotations

from pathlib import Path

import pytest

from vellum import app
from vellum.config import Settings, VellumPaths
from vellum.startup import StartupPrerequisiteError


def test_app_wires_persisted_model_and_vocabulary_hints_to_the_transcription_engine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(vocabulary_hints=("Kubernetes", "Terraform"))
    paths = VellumPaths(tmp_path / "models" / "large-v3-turbo", tmp_path / "Vellum")
    engine_arguments: list[tuple[Path, tuple[str, ...]]] = []
    engine_vocabulary_updates: list[tuple[str, ...]] = []
    updated_settings = Settings(vocabulary_hints=("Helm",))

    class FakeSettingsStore:
        def __init__(self, _: Path) -> None:
            pass

        def load(self) -> Settings:
            return settings

    class FakeTray:
        def __init__(self, _: Settings) -> None:
            self.settings_controller: FakeSettingsController | None = None

        def set_settings_controller(self, controller: FakeSettingsController) -> None:
            self.settings_controller = controller

        def warming(self) -> None:
            pass

        def run(self, _: object) -> bool:
            assert self.settings_controller is not None
            self.settings_controller.save(updated_settings)
            return True

        def feedback(self, _: object) -> None:
            pass

        def report_error(self, _: Exception) -> None:
            pass

        def apply_settings(self, _: Settings) -> None:
            pass

    class FakeEngine:
        def __init__(
            self,
            model_directory: Path,
            vocabulary_hints: tuple[str, ...],
            _: object,
        ) -> None:
            engine_arguments.append((model_directory, vocabulary_hints))

        def start_warming(self) -> None:
            pass

        def set_vocabulary_hints(self, vocabulary_hints: tuple[str, ...]) -> None:
            engine_vocabulary_updates.append(vocabulary_hints)

    class FakeSession:
        active = False

        def __init__(self, **_: object) -> None:
            pass

    class FakeRecorder:
        def __init__(self, **_: object) -> None:
            pass

        def set_input_device(self, _: object) -> None:
            pass

    class FakeSettingsController:
        def __init__(self, _: object, __: object, on_settings_changed: object, ___: object) -> None:
            assert callable(on_settings_changed)
            self._on_settings_changed = on_settings_changed

        def sync_start_at_sign_in(self, _: Settings) -> None:
            pass

        def save(self, updated: Settings) -> None:
            self._on_settings_changed(updated)

    class FakeHotkey:
        def configure(self, _: str) -> None:
            pass

    monkeypatch.setattr(app.sys, "platform", "win32")
    monkeypatch.setattr(app.VellumPaths, "from_environment", lambda: paths)
    monkeypatch.setattr(app, "configure_diagnostics", lambda _: None)
    monkeypatch.setattr(app, "SettingsStore", FakeSettingsStore)
    monkeypatch.setattr(app, "require_startup_prerequisites", lambda _: None)
    monkeypatch.setattr(app, "WindowsPrerequisiteProbe", lambda _: object())
    monkeypatch.setattr(app, "TrayApplication", FakeTray)
    monkeypatch.setattr(app, "SoundDeviceRecorder", FakeRecorder)
    monkeypatch.setattr(app, "AsyncFasterWhisperTranscriptionEngine", FakeEngine)
    monkeypatch.setattr(app, "DictationSession", FakeSession)
    monkeypatch.setattr(app, "WindowsFocus", lambda: object())
    monkeypatch.setattr(app, "WindowsClipboard", lambda: object())
    monkeypatch.setattr(app, "WindowsPaste", lambda: object())
    monkeypatch.setattr(app, "PushToTalkHotkey", lambda *_: FakeHotkey())
    monkeypatch.setattr(app, "WindowsStartAtSignIn", lambda: object())
    monkeypatch.setattr(app, "SettingsController", FakeSettingsController)

    assert app.main() == 0
    assert engine_arguments == [
        (paths.model_directory_for(settings.transcription_model), settings.vocabulary_hints)
    ]
    assert engine_vocabulary_updates == [updated_settings.vocabulary_hints]


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
    monkeypatch.setattr(app, "WindowsPrerequisiteProbe", lambda _: object())

    def fail_prerequisites(_: object) -> None:
        raise StartupPrerequisiteError("CUDA unavailable")

    monkeypatch.setattr(app, "require_startup_prerequisites", fail_prerequisites)

    assert app.main() == 2
    assert events == ["constructed", "failed", "run"]
