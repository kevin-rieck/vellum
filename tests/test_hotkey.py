from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar

import pytest

from vellum import hotkey
from vellum.hotkey import PushToTalkHotkey
from vellum.session import DictationSession, PendingTranscription


class FakeRecorder:
    def __init__(self) -> None:
        self.stopped = False
        self.starts = 0

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> bytes:
        self.stopped = True
        return b"spoken audio"


class FakeEngine:
    def transcribe(self, audio: object) -> str:
        raise AssertionError("Transcription must run on the background thread.")


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


def test_hotkey_stops_capture_at_the_session_duration_limit(
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
    monkeypatch.setattr(hotkey, "Timer", DeferredTimer)
    monkeypatch.setattr(hotkey, "Thread", DeferredThread)
    activation = PushToTalkHotkey(session, lambda _: None)
    activation.enable()

    activation._start_session()
    assert len(timers) == 1
    timer = timers[0]
    timer.function()

    assert recorder.stopped is True
    assert timer.cancelled is True
    assert len(DeferredThread.started) == 1

    finish, args, _ = DeferredThread.started[0]
    assert callable(finish)
    finish(*args)
    activation._start_session()

    assert recorder.starts == 1


def test_hotkey_stops_capture_before_starting_the_transcription_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    DeferredThread.started = []
    recorder = FakeRecorder()
    session = DictationSession(
        recorder=recorder,
        transcription_engine=FakeEngine(),
        focus=FakeFocus(),
        clipboard=FakeClipboard(),
        inserter=FakeInserter(),
        feedback=lambda _: None,
    )
    session.start()
    monkeypatch.setattr(hotkey, "Thread", DeferredThread)

    PushToTalkHotkey(session, lambda _: None)._finish_recording()

    assert recorder.stopped is True
    assert session.active is True
    assert len(DeferredThread.started) == 1
    _, args, daemon = DeferredThread.started[0]
    assert len(args) == 1
    pending = args[0]
    assert isinstance(pending, PendingTranscription)
    assert pending.audio == b"spoken audio"
    assert pending.insertion_target == 101
    assert daemon is True
