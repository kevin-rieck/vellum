from __future__ import annotations

from collections.abc import Callable

from vellum.session import DictationSession, DictationState, SessionFeedback


class Recorder:
    def start(self) -> None:
        pass

    def stop(self) -> bytes:
        return b"audio"


class Engine:
    def transcribe(self, audio: object) -> str:
        return "Transcript"


class Focus:
    def foreground_target(self) -> int:
        return 1


class Clipboard:
    def copy(self, text: str) -> None:
        pass


class Inserter:
    def paste(self, target: object) -> bool:
        return True


def make_session(feedback: Callable[[SessionFeedback], None] | None = None) -> DictationSession:
    return DictationSession(
        recorder=Recorder(),
        transcription_engine=Engine(),
        focus=Focus(),
        clipboard=Clipboard(),
        inserter=Inserter(),
        feedback=feedback or (lambda _: None),
    )


def test_state_machine_exposes_the_capture_and_transcription_boundaries() -> None:
    dictation = make_session()

    assert dictation.state is DictationState.IDLE
    dictation.start()
    assert dictation.state is DictationState.RECORDING
    pending = dictation.end_capture()
    assert dictation.state is DictationState.TRANSCRIBING
    dictation.finish_transcription(pending)
    assert dictation.state is DictationState.IDLE


def test_state_machine_ignores_activation_while_transcribing() -> None:
    dictation = make_session()
    dictation.start()
    pending = dictation.end_capture()

    dictation.start()

    assert dictation.state is DictationState.TRANSCRIBING
    dictation.finish_transcription(pending)
