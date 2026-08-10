from __future__ import annotations

import pytest

from vellum import hotkey
from vellum.hotkey import PushToTalkHotkey
from vellum.session import DictationSession


class FakeRecorder:
    def __init__(self) -> None:
        self.stopped = False

    def start(self) -> None:
        pass

    def stop(self) -> bytes:
        self.stopped = True
        return b"spoken audio"


class FakeEngine:
    def transcribe(self, audio: object) -> str:
        raise AssertionError("Transcription must run on the background thread.")


class FakeFocus:
    def foreground_target(self) -> int:
        return 101


class FakeClipboard:
    def copy(self, text: str) -> None:
        pass


class FakeInserter:
    def paste(self, insertion_target: object) -> bool:
        return True


def test_hotkey_stops_capture_before_starting_the_transcription_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[tuple[object, tuple[object, ...], bool]] = []

    class DeferredThread:
        def __init__(self, *, target: object, args: tuple[object, ...], daemon: bool) -> None:
            started.append((target, args, daemon))

        def start(self) -> None:
            pass

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

    PushToTalkHotkey(session, lambda _: None)._finish_from_release()

    assert recorder.stopped is True
    assert session.active is True
    assert len(started) == 1
    _, args, daemon = started[0]
    assert args == (b"spoken audio", 101)
    assert daemon is True
