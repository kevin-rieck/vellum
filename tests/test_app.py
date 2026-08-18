from __future__ import annotations

from pathlib import Path

import pytest

from vellum import app
from vellum.config import Settings, VellumPaths
from vellum.startup import StartupPrerequisiteError


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
