from __future__ import annotations

import sys
from collections.abc import Callable
from types import SimpleNamespace
from typing import ClassVar

import pytest

from vellum import hotkey
from vellum.hotkey import PushToTalkHotkey
from vellum.session import DictationSession


class FakeRecorder:
    def __init__(self) -> None:
        self.stopped = False
        self.starts = 0
        self.stops = 0

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> bytes:
        self.stopped = True
        self.stops += 1
        return b"spoken audio"


class SuccessfulFakeEngine:
    def transcribe(self, audio: object) -> str:
        return "transcript"


class FakeFocus:
    def foreground_target(self) -> int:
        return 101


class FakeClipboard:
    def copy(self, text: str) -> None:
        pass


class FakeInserter:
    def paste(self, insertion_target: object) -> bool:
        return True


class DeferredThread:
    started: ClassVar[list[tuple[object, tuple[object, ...], bool]]] = []

    def __init__(self, *, target: object, args: tuple[object, ...], daemon: bool) -> None:
        self.started.append((target, args, daemon))

    def start(self) -> None:
        pass


def test_hotkey_ends_capture_at_the_duration_limit_and_cancels_the_next_timer_on_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    DeferredThread.started = []

    class DeferredTimer:
        def __init__(self, interval: float, function: Callable[[], None]) -> None:
            assert interval == 60
            self.function = function
            self.cancelled = False
            timers.append(self)

        def start(self) -> None:
            pass

        def cancel(self) -> None:
            self.cancelled = True

    class Listener:
        instance: ClassVar[Listener | None] = None

        def __init__(
            self,
            *,
            on_press: Callable[[object], None],
            on_release: Callable[[object], None],
        ) -> None:
            self.on_press = on_press
            self.on_release = on_release
            type(self).instance = self

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    key = SimpleNamespace(
        ctrl=object(),
        ctrl_l=object(),
        ctrl_r=object(),
        alt=object(),
        alt_l=object(),
        alt_r=object(),
        space=object(),
    )
    timers: list[DeferredTimer] = []
    recorder = FakeRecorder()
    session = DictationSession(
        recorder=recorder,
        transcription_engine=SuccessfulFakeEngine(),
        focus=FakeFocus(),
        clipboard=FakeClipboard(),
        inserter=FakeInserter(),
        feedback=lambda _: None,
    )
    monkeypatch.setitem(
        sys.modules,
        "pynput",
        SimpleNamespace(keyboard=SimpleNamespace(Key=key, Listener=Listener)),
    )
    monkeypatch.setattr(hotkey, "Timer", DeferredTimer)
    monkeypatch.setattr(hotkey, "Thread", DeferredThread)
    activation = PushToTalkHotkey(session, lambda _: None)
    activation.enable()
    activation.start()

    assert Listener.instance is not None
    Listener.instance.on_press(key.ctrl)
    Listener.instance.on_press(key.alt)
    Listener.instance.on_press(key.space)
    assert len(timers) == 1

    timer = timers[0]
    timer.function()

    assert recorder.stopped is True
    assert recorder.stops == 1
    assert timer.cancelled is True
    assert len(DeferredThread.started) == 1

    finish, args, _ = DeferredThread.started[0]
    assert callable(finish)
    finish(*args)
    Listener.instance.on_release(key.space)
    Listener.instance.on_press(key.space)

    assert recorder.starts == 2
    next_timer = timers[1]
    Listener.instance.on_press(key.ctrl_l)
    Listener.instance.on_release(key.ctrl_l)
    assert recorder.stops == 1
    activation.stop()
    assert next_timer.cancelled is True
    next_timer.function()
    assert recorder.stops == 1
