"""The public Dictation session lifecycle seam."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Protocol, TypeAlias

Audio: TypeAlias = object
InsertionTarget: TypeAlias = object


class Recorder(Protocol):
    def start(self) -> None: ...

    def stop(self) -> Audio: ...


class TranscriptionEngine(Protocol):
    def transcribe(self, audio: Audio) -> str: ...


class FocusReader(Protocol):
    def foreground_target(self) -> InsertionTarget: ...


class Clipboard(Protocol):
    def copy(self, text: str) -> None: ...


class Inserter(Protocol):
    def paste(self) -> None: ...


class SessionFeedback(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    CANCELLED = "cancelled"
    NO_SPEECH = "no-speech"
    ERROR = "error"


class DictationSession:
    """Runs one Push-to-talk Dictation session at a time.

    The insertion target is captured at hotkey release, before transcription.
    Clipboard copy deliberately precedes the focus recheck so a cancelled insertion
    still leaves the Transcript available to the user.
    """

    def __init__(
        self,
        *,
        recorder: Recorder,
        transcription_engine: TranscriptionEngine,
        focus: FocusReader,
        clipboard: Clipboard,
        inserter: Inserter,
        feedback: Callable[[SessionFeedback], None],
    ) -> None:
        self._recorder = recorder
        self._transcription_engine = transcription_engine
        self._focus = focus
        self._clipboard = clipboard
        self._inserter = inserter
        self._feedback = feedback
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        """Start capture if this is not already an active Dictation session."""
        if self._active:
            return
        self._recorder.start()
        self._active = True
        self._feedback(SessionFeedback.RECORDING)

    def capture_insertion_target(self) -> InsertionTarget:
        """Capture the foreground application at the precise hotkey-release boundary."""
        if not self._active:
            raise RuntimeError("No Dictation session is active.")
        return self._focus.foreground_target()

    def fail_release(self) -> None:
        """Close capture if the release-time Insertion target cannot be identified."""
        if not self._active:
            return
        try:
            self._recorder.stop()
        finally:
            self._active = False
            self._feedback(SessionFeedback.ERROR)

    def finish(self, insertion_target: InsertionTarget | None = None) -> None:
        """End capture, transcribe locally, then insert only into the release target.

        The hotkey adapter supplies the target captured in its release callback.
        The optional fallback keeps this public seam convenient for direct callers.
        """
        if not self._active:
            return

        capture_stopped = False
        try:
            if insertion_target is None:
                insertion_target = self.capture_insertion_target()
            audio = self._recorder.stop()
            capture_stopped = True
            self._feedback(SessionFeedback.TRANSCRIBING)
            transcript = self._transcription_engine.transcribe(audio)
            if not transcript.strip():
                self._feedback(SessionFeedback.NO_SPEECH)
                return

            self._clipboard.copy(transcript)
            if self._focus.foreground_target() != insertion_target:
                self._feedback(SessionFeedback.CANCELLED)
                return
            self._inserter.paste()
            self._feedback(SessionFeedback.IDLE)
        except Exception:
            if not capture_stopped:
                try:
                    self._recorder.stop()
                except Exception:
                    pass
            self._feedback(SessionFeedback.ERROR)
            raise
        finally:
            self._active = False
