from __future__ import annotations

from collections.abc import Callable
from threading import Event, Thread

import pytest

from vellum.session import DictationSession, SessionFeedback


class FakeRecorder:
    def __init__(
        self,
        *,
        stop_error: Exception | None = None,
        on_stop: Callable[[], None] | None = None,
    ) -> None:
        self.started = False
        self.starts = 0
        self.audio = b"spoken audio"
        self.stop_error = stop_error
        self.on_stop = on_stop

    def start(self) -> None:
        self.started = True
        self.starts += 1

    def stop(self) -> bytes:
        if self.stop_error is not None:
            raise self.stop_error
        self.started = False
        if self.on_stop is not None:
            self.on_stop()
        return self.audio


class FakeTranscriptionEngine:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.audio: object | None = None

    def transcribe(self, audio: object) -> str:
        self.audio = audio
        return self.transcript


class FakeFocus:
    def __init__(self, target: int) -> None:
        self.target = target

    def foreground_target(self) -> int:
        return self.target


class FakeClipboard:
    def __init__(self) -> None:
        self.text: str | None = None

    def copy(self, text: str) -> None:
        self.text = text


class FakeInserter:
    def __init__(self, *, can_paste: bool = True) -> None:
        self.can_paste = can_paste
        self.inserted = False
        self.target: object | None = None

    def paste(self, insertion_target: object) -> bool:
        self.target = insertion_target
        if not self.can_paste:
            return False
        self.inserted = True
        return True


def session(
    *,
    focus: FakeFocus,
    transcript: str = "ship the tracer bullet",
    feedback: Callable[[SessionFeedback], None] | None = None,
) -> tuple[DictationSession, FakeClipboard, FakeInserter]:
    clipboard = FakeClipboard()
    inserter = FakeInserter()
    return (
        DictationSession(
            recorder=FakeRecorder(),
            transcription_engine=FakeTranscriptionEngine(transcript),
            focus=focus,
            clipboard=clipboard,
            inserter=inserter,
            feedback=feedback or (lambda _: None),
        ),
        clipboard,
        inserter,
    )


def test_start_feedback_failure_closes_capture_and_leaves_the_session_inactive() -> None:
    recorder = FakeRecorder()

    def failing_feedback(_: SessionFeedback) -> None:
        raise RuntimeError("tray unavailable")

    dictation = DictationSession(
        recorder=recorder,
        transcription_engine=FakeTranscriptionEngine("ship the tracer bullet"),
        focus=FakeFocus(target=101),
        clipboard=FakeClipboard(),
        inserter=FakeInserter(),
        feedback=failing_feedback,
    )

    with pytest.raises(RuntimeError, match="tray unavailable"):
        dictation.start()

    assert recorder.started is False
    assert dictation.active is False


def test_start_feedback_and_cleanup_failures_leave_capture_active_and_are_preserved() -> None:
    feedback_error = RuntimeError("tray unavailable")
    cleanup_error = RuntimeError("microphone unavailable")
    recorder = FakeRecorder(stop_error=cleanup_error)

    def failing_feedback(_: SessionFeedback) -> None:
        raise feedback_error

    dictation = DictationSession(
        recorder=recorder,
        transcription_engine=FakeTranscriptionEngine("ship the tracer bullet"),
        focus=FakeFocus(target=101),
        clipboard=FakeClipboard(),
        inserter=FakeInserter(),
        feedback=failing_feedback,
    )

    with pytest.raises(ExceptionGroup) as raised:
        dictation.start()

    assert raised.value.exceptions == (feedback_error, cleanup_error)
    assert recorder.started is True
    assert dictation.active is True


def test_releasing_push_to_talk_copies_raw_transcript_and_pastes_into_unchanged_target() -> None:
    focus = FakeFocus(target=101)
    dictation, clipboard, inserter = session(focus=focus)

    dictation.start()
    dictation.finish()

    assert clipboard.text == "ship the tracer bullet"
    assert inserter.inserted is True


def test_transcript_stays_in_clipboard_when_insertion_target_changes() -> None:
    focus = FakeFocus(target=101)
    events: list[SessionFeedback] = []
    dictation, clipboard, inserter = session(focus=focus, feedback=events.append)

    dictation.start()
    pending = dictation.end_capture()
    focus.target = 202
    dictation.finish_transcription(pending)

    assert clipboard.text == "ship the tracer bullet"
    assert inserter.inserted is False
    assert events == [
        SessionFeedback.RECORDING,
        SessionFeedback.TRANSCRIBING,
        SessionFeedback.CANCELLED,
        SessionFeedback.IDLE,
    ]


def test_capture_end_stops_capture_before_identifying_the_insertion_target() -> None:
    focus = FakeFocus(target=101)
    recorder = FakeRecorder(on_stop=lambda: setattr(focus, "target", 202))
    dictation = DictationSession(
        recorder=recorder,
        transcription_engine=FakeTranscriptionEngine("ship the tracer bullet"),
        focus=focus,
        clipboard=FakeClipboard(),
        inserter=FakeInserter(),
        feedback=lambda _: None,
    )

    dictation.start()
    pending = dictation.end_capture()

    assert recorder.started is False
    assert pending.insertion_target == 202


def test_capture_end_target_failure_closes_capture() -> None:
    class FailingFocus:
        def foreground_target(self) -> int:
            raise RuntimeError("focus unavailable")

    events: list[SessionFeedback] = []
    dictation = DictationSession(
        recorder=FakeRecorder(),
        transcription_engine=FakeTranscriptionEngine("ship the tracer bullet"),
        focus=FailingFocus(),
        clipboard=FakeClipboard(),
        inserter=FakeInserter(),
        feedback=events.append,
    )

    dictation.start()
    with pytest.raises(RuntimeError, match="focus unavailable"):
        dictation.end_capture()

    assert dictation.active is False
    assert events == [SessionFeedback.RECORDING, SessionFeedback.ERROR]


def test_stale_target_at_the_insertion_boundary_preserves_the_transcript() -> None:
    focus = FakeFocus(target=101)
    events: list[SessionFeedback] = []
    clipboard = FakeClipboard()
    inserter = FakeInserter(can_paste=False)
    dictation = DictationSession(
        recorder=FakeRecorder(),
        transcription_engine=FakeTranscriptionEngine("ship the tracer bullet"),
        focus=focus,
        clipboard=clipboard,
        inserter=inserter,
        feedback=events.append,
    )

    dictation.start()
    dictation.finish()

    assert clipboard.text == "ship the tracer bullet"
    assert inserter.inserted is False
    assert inserter.target == 101
    assert events == [
        SessionFeedback.RECORDING,
        SessionFeedback.TRANSCRIBING,
        SessionFeedback.CANCELLED,
        SessionFeedback.IDLE,
    ]


def test_start_is_ignored_until_transcription_finishes() -> None:
    class BlockingEngine(FakeTranscriptionEngine):
        def __init__(self) -> None:
            super().__init__("ship the tracer bullet")
            self.entered = Event()
            self.release = Event()

        def transcribe(self, audio: object) -> str:
            self.entered.set()
            assert self.release.wait(timeout=1)
            return super().transcribe(audio)

    recorder = FakeRecorder()
    engine = BlockingEngine()
    dictation = DictationSession(
        recorder=recorder,
        transcription_engine=engine,
        focus=FakeFocus(target=101),
        clipboard=FakeClipboard(),
        inserter=FakeInserter(),
        feedback=lambda _: None,
    )

    dictation.start()
    pending = dictation.end_capture()
    assert recorder.started is False
    finishing = Thread(target=dictation.finish_transcription, args=(pending,))
    finishing.start()
    assert engine.entered.wait(timeout=1)
    dictation.start()

    assert recorder.starts == 1
    engine.release.set()
    finishing.join(timeout=1)
    assert dictation.active is False

    dictation.start()
    assert recorder.starts == 2


def test_no_speech_preserves_the_existing_clipboard_without_pasting() -> None:
    focus = FakeFocus(target=101)
    events: list[SessionFeedback] = []
    dictation, clipboard, inserter = session(focus=focus, transcript="  ", feedback=events.append)
    clipboard.text = "existing clipboard text"

    dictation.start()
    dictation.finish()

    assert clipboard.text == "existing clipboard text"
    assert inserter.inserted is False
    assert events == [
        SessionFeedback.RECORDING,
        SessionFeedback.TRANSCRIBING,
        SessionFeedback.NO_SPEECH,
        SessionFeedback.IDLE,
    ]
