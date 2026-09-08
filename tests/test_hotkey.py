from __future__ import annotations

import sys
from collections.abc import Callable
from types import SimpleNamespace
from typing import ClassVar

import pytest

from vellum import hotkey
from vellum.hotkey import PushToTalkHotkey
from vellum.session import DictationSession, SessionFeedback


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


def make_session(
    recorder: FakeRecorder,
    feedback: Callable[[SessionFeedback], None] | None = None,
) -> DictationSession:
    return DictationSession(
        recorder=recorder,
        transcription_engine=SuccessfulFakeEngine(),
        focus=FakeFocus(),
        clipboard=FakeClipboard(),
        inserter=FakeInserter(),
        feedback=feedback or (lambda _: None),
    )


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
    monkeypatch.setitem(
        sys.modules,
        "pynput",
        SimpleNamespace(keyboard=SimpleNamespace(Key=key, Listener=Listener)),
    )
    monkeypatch.setattr(hotkey, "Timer", DeferredTimer)
    monkeypatch.setattr(hotkey, "Thread", DeferredThread)
    activation = PushToTalkHotkey(make_session(recorder), lambda _: None)
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


def test_key_release_recovers_capture_after_start_feedback_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    DeferredThread.started = []
    feedback_error = RuntimeError("tray unavailable")
    cleanup_error = RuntimeError("microphone unavailable")

    class RecorderWithTransientCleanupFailure(FakeRecorder):
        def stop(self) -> bytes:
            self.stops += 1
            if self.stops == 1:
                raise cleanup_error
            self.stopped = True
            return b"spoken audio"

    class DeferredTimer:
        def __init__(self, interval: float, function: Callable[[], None]) -> None:
            assert interval == 60
            self.function = function

        def start(self) -> None:
            pass

        def cancel(self) -> None:
            pass

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
    events: list[SessionFeedback] = []

    def feedback(event: SessionFeedback) -> None:
        events.append(event)
        if event is SessionFeedback.RECORDING and events.count(SessionFeedback.RECORDING) == 1:
            raise feedback_error

    recorder = RecorderWithTransientCleanupFailure()
    errors: list[Exception] = []
    monkeypatch.setitem(
        sys.modules,
        "pynput",
        SimpleNamespace(keyboard=SimpleNamespace(Key=key, Listener=Listener)),
    )
    monkeypatch.setattr(hotkey, "Timer", DeferredTimer)
    monkeypatch.setattr(hotkey, "Thread", DeferredThread)
    activation = PushToTalkHotkey(make_session(recorder, feedback), errors.append)
    activation.enable()
    activation.start()

    assert Listener.instance is not None
    Listener.instance.on_press(key.ctrl)
    Listener.instance.on_press(key.alt)
    Listener.instance.on_press(key.space)

    assert len(errors) == 1
    assert isinstance(errors[0], ExceptionGroup)
    assert errors[0].exceptions == (feedback_error, cleanup_error)
    assert recorder.stops == 1

    Listener.instance.on_release(key.space)

    assert recorder.stops == 2
    assert len(DeferredThread.started) == 1
    finish, args, _ = DeferredThread.started[0]
    finish(*args)

    Listener.instance.on_press(key.space)
    assert recorder.starts == 2


def test_configured_activation_hotkey_starts_and_ends_push_to_talk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    DeferredThread.started = []

    class DeferredTimer:
        def __init__(self, interval: float, function: Callable[[], None]) -> None:
            self.function = function

        def start(self) -> None:
            pass

        def cancel(self) -> None:
            pass

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
        shift=object(),
        shift_l=object(),
        shift_r=object(),
    )

    class CharacterKey:
        def __init__(self, char: str) -> None:
            self.char = char

    recorder = FakeRecorder()
    monkeypatch.setitem(
        sys.modules,
        "pynput",
        SimpleNamespace(keyboard=SimpleNamespace(Key=key, Listener=Listener)),
    )
    monkeypatch.setattr(hotkey, "Timer", DeferredTimer)
    monkeypatch.setattr(hotkey, "Thread", DeferredThread)
    activation = PushToTalkHotkey(make_session(recorder), lambda _: None, "Ctrl+Shift+D")
    activation.enable()
    activation.start()

    assert Listener.instance is not None
    Listener.instance.on_press(key.ctrl)
    Listener.instance.on_press(key.shift)
    Listener.instance.on_press(CharacterKey("d"))

    assert recorder.starts == 1
    assert activation.activation_hotkey == "Ctrl+Shift+D"

    Listener.instance.on_release(CharacterKey("d"))

    assert recorder.stops == 1
    assert len(DeferredThread.started) == 1


def test_shifted_digit_activation_hotkey_matches_its_virtual_key() -> None:
    keyboard = SimpleNamespace(Key=SimpleNamespace())

    assert hotkey._matches_activation_key(keyboard, SimpleNamespace(char="!", vk=49), "1")
