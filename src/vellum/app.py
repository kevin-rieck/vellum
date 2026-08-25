"""Developer entry point for the Vellum tray application."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence

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
from vellum.transcription_engines import (
    SUPPORTED_TRANSCRIPTION_ENGINES,
    EngineDownloadProgress,
    EngineInstaller,
    EngineVerifier,
    TranscriptionEngineId,
    TranscriptionEngineVerificationError,
    transcription_engine_by_id,
)
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
        tray = TrayApplication(settings)
    except RuntimeError as error:
        log_error(error)
        return 2

    recorder: SoundDeviceRecorder | None = None
    session: DictationSession | None = None
    transcription_engine: AsyncFasterWhisperTranscriptionEngine | None = None
    hotkey: PushToTalkHotkey | None = None
    runtime_started = False

    def can_apply_settings(updated_settings: Settings) -> None:
        del updated_settings
        if session is not None and session.active:
            raise RuntimeError("Release Push-to-talk before saving Settings.")

    def apply_settings(updated_settings: Settings) -> None:
        if recorder is not None:
            recorder.set_input_device(updated_settings.input_device)
        if hotkey is not None:
            hotkey.configure(updated_settings.activation_hotkey)
        if transcription_engine is not None:
            transcription_engine.set_vocabulary_hints(
                updated_settings.transcription_vocabulary_hints
            )
        tray.apply_settings(updated_settings)

    settings_controller = SettingsController(
        settings_store,
        WindowsStartAtSignIn(),
        apply_settings,
        can_apply_settings,
        current_settings=settings,
    )
    tray.set_settings_controller(settings_controller)

    def prerequisite_probe(engine_id: TranscriptionEngineId) -> WindowsPrerequisiteProbe:
        descriptor = transcription_engine_by_id(engine_id)
        return WindowsPrerequisiteProbe(paths.engine_directory, descriptor)

    def engine_available(engine_id: TranscriptionEngineId) -> bool:
        descriptor = transcription_engine_by_id(engine_id)
        probe = prerequisite_probe(engine_id)
        if not getattr(probe, "engine_available", True):
            return False
        try:
            EngineVerifier().verify(descriptor, paths.engine_directory)
        except TranscriptionEngineVerificationError:
            return False
        return True

    def cuda_available(engine_id: TranscriptionEngineId) -> bool:
        return getattr(prerequisite_probe(engine_id), "cuda_available", True)

    def start_runtime(
        updated_settings: Settings, *, engine_verified: bool = False
    ) -> PushToTalkHotkey:
        nonlocal recorder, session, transcription_engine
        descriptor = transcription_engine_by_id(updated_settings.transcription_engine_id)
        require_startup_prerequisites(prerequisite_probe(updated_settings.transcription_engine_id))
        if not engine_verified:
            EngineVerifier().verify(descriptor, paths.engine_directory)
        recorder = SoundDeviceRecorder(input_device=updated_settings.input_device)
        runtime_hotkey: PushToTalkHotkey | None = None

        def warmed(error: Exception | None) -> None:
            if error is not None:
                tray.fail_startup(error)
                return
            if runtime_hotkey is None:
                tray.fail_startup(RuntimeError("The Activation hotkey was not configured."))
                return
            runtime_hotkey.enable()
            tray.feedback(SessionFeedback.IDLE)

        transcription_engine = AsyncFasterWhisperTranscriptionEngine(
            paths.engine_directory, updated_settings.transcription_vocabulary_hints, warmed
        )
        session = DictationSession(
            recorder=recorder,
            transcription_engine=transcription_engine,
            focus=WindowsFocus(),
            clipboard=WindowsClipboard(),
            inserter=WindowsPaste(),
            feedback=tray.feedback,
        )
        runtime_hotkey = PushToTalkHotkey(
            session, tray.report_error, updated_settings.activation_hotkey
        )
        tray.warming()
        transcription_engine.start_warming()
        return runtime_hotkey

    def download_engine(
        updated_settings: Settings, on_progress: Callable[[EngineDownloadProgress], None]
    ) -> None:
        nonlocal hotkey, runtime_started
        descriptor = transcription_engine_by_id(updated_settings.transcription_engine_id)
        EngineInstaller(paths.engine_directory).install(descriptor, on_progress)
        if runtime_started:
            return
        try:
            hotkey = start_runtime(updated_settings, engine_verified=True)
        except (RuntimeError, StartupPrerequisiteError) as error:
            tray.fail_startup(error)
            raise
        runtime_started = True
        tray.activate_hotkey(hotkey)

    tray.set_engine_onboarding(
        SUPPORTED_TRANSCRIPTION_ENGINES,
        lambda descriptor: engine_available(descriptor.id),
        download_engine,
    )

    try:
        hotkey = start_runtime(settings)
    except (RuntimeError, StartupPrerequisiteError) as error:
        if not engine_available(settings.transcription_engine_id):
            tray.engine_setup_required()
            if not cuda_available(settings.transcription_engine_id):
                tray.report_error(error)
            elif settings_load_error is not None:
                tray.report_error(settings_load_error)
            return 0 if tray.run() else 2
        tray.fail_startup(error)
        return 0 if tray.run() else 2

    runtime_started = True
    if settings_load_error is not None:
        tray.report_error(settings_load_error)
    else:
        try:
            settings_controller.sync_start_at_sign_in(settings)
        except RuntimeError as error:
            tray.report_error(error)

    try:
        return 0 if tray.run(hotkey) else 2
    except RuntimeError as error:
        tray.report_error(error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
