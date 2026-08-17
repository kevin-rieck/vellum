from __future__ import annotations

import sys
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from vellum import tray
from vellum.config import Settings
from vellum.session import SessionFeedback


class FakeSounds:
    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self.events: list[str] = []

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def play_start(self) -> None:
        if self.enabled:
            self.events.append("start")

    def play_end(self) -> None:
        if self.enabled:
            self.events.append("end")


class FakeIcon:
    def __init__(self, name: str, image: object, title: str, menu: object) -> None:
        self.name = name
        self.icon = image
        self.title = title
        self.menu = menu
        self.notifications: list[tuple[str, str]] = []
        self.stopped = False

    def run(self, setup: Callable[[FakeIcon], None] | None = None) -> None:
        if setup is not None:
            setup(self)

    def stop(self) -> None:
        self.stopped = True

    def notify(self, message: str, title: str) -> None:
        self.notifications.append((message, title))


@pytest.fixture
def tray_application(monkeypatch: pytest.MonkeyPatch) -> tray.TrayApplication:
    class FakeMenu:
        def __init__(self, *items: object) -> None:
            self.items = items

    class FakeMenuItem:
        def __init__(self, text: str, callback: object) -> None:
            self.text = text
            self.callback = callback

    class FakeImage:
        @staticmethod
        def new(*_: object) -> object:
            return object()

    class FakeImageDraw:
        @staticmethod
        def Draw(image: object) -> SimpleNamespace:
            del image
            return SimpleNamespace(ellipse=lambda *_args, **_kwargs: None)

    monkeypatch.setitem(
        sys.modules,
        "pystray",
        SimpleNamespace(Icon=FakeIcon, Menu=FakeMenu, MenuItem=FakeMenuItem),
    )
    monkeypatch.setitem(
        sys.modules,
        "PIL",
        SimpleNamespace(Image=FakeImage, ImageDraw=FakeImageDraw),
    )
    monkeypatch.setattr(tray, "WindowsSessionSounds", FakeSounds)
    return tray.TrayApplication(Settings(activation_hotkey="Ctrl+Shift+D"))


def test_tray_exposes_settings_and_communicates_session_feedback(
    tray_application: tray.TrayApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tray, "log_error", lambda _: None)
    icon = tray_application._icon

    assert [item.text for item in icon.menu.items] == ["Settings", "Quit"]
    assert icon.title == "Vellum — ready (Ctrl+Shift+D)"

    tray_application.feedback(SessionFeedback.RECORDING)
    tray_application.feedback(SessionFeedback.TRANSCRIBING)
    tray_application.feedback(SessionFeedback.CANCELLED)
    tray_application.report_error(RuntimeError("microphone unavailable"))

    assert icon.notifications == []
    assert tray_application.run() is True
    assert tray_application._sounds.events == ["start", "end"]
    assert icon.title == "Vellum — error"
    assert icon.notifications == [
        (
            "The insertion target changed. The Transcript is available in the clipboard.",
            "Vellum insertion cancelled",
        ),
        ("microphone unavailable", "Vellum error"),
    ]


def test_disabling_sounds_suppresses_capture_cues(tray_application: tray.TrayApplication) -> None:
    tray_application.apply_settings(Settings(sounds_enabled=False))

    tray_application.feedback(SessionFeedback.RECORDING)
    tray_application.feedback(SessionFeedback.TRANSCRIBING)

    assert tray_application._sounds.events == []
