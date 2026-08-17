"""Developer entry point for the Vellum tray application."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from vellum.config import Settings, SettingsError, SettingsStore, VellumPaths
from vellum.diagnostics import configure_diagnostics, log_error
from vellum.hotkey import PushToTalkHotkey
from vellum.runtime import (
    AsyncFasterWhisperTranscriptionEngine,
    SoundDeviceRecorder,
    WindowsPrerequisiteProbe,
)
from vellum.session import DictationSession, SessionFeedback
from vellum.settings import SettingsController
from vellum.startup import StartupPrerequisiteError, require_startup_prerequisites
from vellum.tray import TrayApplication
from vellum.windows import WindowsClipboard, WindowsFocus, WindowsPaste, WindowsStartAtSignIn


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the local Push-to-talk Dictation application."""
    del arguments
    if sys.platform != "win32":
        print("Vellum requires Windows.", file=sys.stderr)
        return 2

    paths = VellumPaths.from_environment()
    configure_diagnostics(paths.diagnostics_log_file)
    settings_store = SettingsStore(paths.settings_file)
    settings_load_error: SettingsError | None = None
    try:
        settings = settings_store.load()
    except SettingsError as error:
        # Do not overwrite a malformed file or silently replace a selected device.
        settings = Settings()
        settings_load_error = error

    try:
        require_startup_prerequisites(WindowsPrerequisiteProbe(paths.model_directory))
        tray = TrayApplication(settings)
    except (RuntimeError, StartupPrerequisiteError) as error:
        log_error(error)
        return 2

    recorder = SoundDeviceRecorder(input_device=settings.input_device)

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
        recorder=recorder,
        transcription_engine=transcription_engine,
        focus=WindowsFocus(),
        clipboard=WindowsClipboard(),
        inserter=WindowsPaste(),
        feedback=tray.feedback,
    )
    hotkey = PushToTalkHotkey(session, tray.report_error, settings.activation_hotkey)

    def can_apply_settings(updated_settings: Settings) -> None:
        del updated_settings
        if session.active:
            raise RuntimeError("Release Push-to-talk before saving Settings.")

    def apply_settings(updated_settings: Settings) -> None:
        recorder.set_input_device(updated_settings.input_device)
        hotkey.configure(updated_settings.activation_hotkey)
        tray.apply_settings(updated_settings)

    settings_controller = SettingsController(
        settings_store,
        WindowsStartAtSignIn(),
        apply_settings,
        can_apply_settings,
    )
    tray.set_settings_controller(settings_controller)
    if settings_load_error is not None:
        tray.report_error(settings_load_error)
    else:
        try:
            settings_controller.sync_start_at_sign_in(settings)
        except RuntimeError as error:
            tray.report_error(error)

    tray.warming()
    transcription_engine.start_warming()

    try:
        return 0 if tray.run(hotkey) else 2
    except RuntimeError as error:
        tray.report_error(error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
