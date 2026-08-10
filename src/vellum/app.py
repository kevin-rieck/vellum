"""Developer entry point for the Vellum tracer bullet."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from vellum.config import VellumPaths
from vellum.diagnostics import configure_diagnostics, log_error
from vellum.hotkey import PushToTalkHotkey
from vellum.runtime import (
    AsyncFasterWhisperTranscriptionEngine,
    SoundDeviceRecorder,
    WindowsPrerequisiteProbe,
)
from vellum.session import DictationSession, SessionFeedback
from vellum.startup import StartupPrerequisiteError, require_startup_prerequisites
from vellum.tray import TrayApplication
from vellum.windows import WindowsClipboard, WindowsFocus, WindowsPaste


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the local Ctrl+Alt+Space Dictation application."""
    del arguments
    if sys.platform != "win32":
        print("Vellum requires Windows.", file=sys.stderr)
        return 2

    paths = VellumPaths.from_environment()
    configure_diagnostics(paths.diagnostics_log_file)
    try:
        require_startup_prerequisites(WindowsPrerequisiteProbe(paths.model_directory))
        tray = TrayApplication()
    except (RuntimeError, StartupPrerequisiteError) as error:
        log_error(error)
        return 2

    def warmed(error: Exception | None) -> None:
        if error is None:
            hotkey.enable()
            tray.feedback(SessionFeedback.IDLE)
            return
        tray.fail_startup(error)

    transcription_engine = AsyncFasterWhisperTranscriptionEngine(
        paths.model_directory, paths.vocabulary_hints, warmed
    )
    session = DictationSession(
        recorder=SoundDeviceRecorder(),
        transcription_engine=transcription_engine,
        focus=WindowsFocus(),
        clipboard=WindowsClipboard(),
        inserter=WindowsPaste(),
        feedback=tray.feedback,
    )
    hotkey = PushToTalkHotkey(session, tray.report_error)
    tray.warming()
    transcription_engine.start_warming()

    try:
        return 0 if tray.run(hotkey) else 2
    except RuntimeError as error:
        tray.report_error(error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
