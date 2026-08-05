from __future__ import annotations

from collections.abc import Callable

from vellum.session import DictationSession, SessionFeedback


class FakeRecorder:
    def __init__(self) -> None:
        self.started = False
        self.audio = b"spoken audio"

    def start(self) -> None:
        self.started = True

    def stop(self) -> bytes:
        self.started = False
        return self.audio


class FakeTranscriptionEngine:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.audio: bytes | None = None

    def transcribe(self, audio: bytes) -> str:
        self.audio = audio
        return self.transcript


class FakeFocus:
    def __init__(self, target: int, changes_to: int | None = None) -> None:
        self.target = target
        self.changes_to = changes_to

    def foreground_target(self) -> int:
        target = self.target
        if self.changes_to is not None:
            self.target = self.changes_to
            self.changes_to = None
        return target


class FakeClipboard:
    def __init__(self) -> None:
        self.text: str | None = None

    def copy(self, text: str) -> None:
        self.text = text


class FakeInserter:
    def __init__(self) -> None:
        self.inserted = False

    def paste(self) -> None:
        self.inserted = True


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


def test_releasing_push_to_talk_copies_raw_transcript_and_pastes_into_unchanged_target() -> None:
    focus = FakeFocus(target=101)
    dictation, clipboard, inserter = session(focus=focus)

    dictation.start()
    dictation.finish()

    assert clipboard.text == "ship the tracer bullet"
    assert inserter.inserted is True


def test_transcript_stays_in_clipboard_when_insertion_target_changes() -> None:
    focus = FakeFocus(target=101, changes_to=202)
    events: list[SessionFeedback] = []
    dictation, clipboard, inserter = session(focus=focus, feedback=events.append)

    dictation.start()
    release_target = dictation.capture_insertion_target()
    focus.target = 202
    dictation.finish(release_target)

    assert clipboard.text == "ship the tracer bullet"
    assert inserter.inserted is False
    assert events == [
        SessionFeedback.RECORDING,
        SessionFeedback.TRANSCRIBING,
        SessionFeedback.CANCELLED,
    ]


def test_release_target_failure_closes_capture() -> None:
    focus = FakeFocus(target=101)
    events: list[SessionFeedback] = []
    dictation, _, _ = session(focus=focus, feedback=events.append)

    dictation.start()
    dictation.fail_release()

    assert dictation.active is False
    assert events == [SessionFeedback.RECORDING, SessionFeedback.ERROR]


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
    ]
