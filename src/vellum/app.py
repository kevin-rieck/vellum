"""Developer entry point for the Vellum tray application."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence

from vellum.config import Settings, SettingsError, SettingsStore, VellumPaths
from vellum.diagnostics import configure_diagnostics, log_error
from vellum.hotkey import PushToTalkHotkey
from vellum.models import (
    SUPPORTED_MODELS,
    ModelDownloadProgress,
    ModelInstaller,
    ModelVerificationError,
    ModelVerifier,
    model_by_id,
)
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

    def model_files_available(model_id: str) -> bool:
        descriptor = model_by_id(model_id)
        probe = WindowsPrerequisiteProbe(paths.model_directory, descriptor)
        return getattr(probe, "model_available", True)

    def model_available(model_id: str) -> bool:
        descriptor = model_by_id(model_id)
        if not model_files_available(model_id):
            return False
        try:
            ModelVerifier().verify(descriptor, paths.model_directory)
        except ModelVerificationError:
            return False
        return True

    def cuda_available(model_id: str) -> bool:
        descriptor = model_by_id(model_id)
        probe = WindowsPrerequisiteProbe(paths.model_directory, descriptor)
        return getattr(probe, "cuda_available", True)

    def start_runtime(
        updated_settings: Settings, *, model_verified: bool = False
    ) -> PushToTalkHotkey:
        nonlocal recorder, session, transcription_engine
        descriptor = model_by_id(updated_settings.model_id)
        require_startup_prerequisites(WindowsPrerequisiteProbe(paths.model_directory, descriptor))
        if not model_verified:
            ModelVerifier().verify(descriptor, paths.model_directory)
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
            paths.model_directory, updated_settings.transcription_vocabulary_hints, warmed
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

    def download_model(
        updated_settings: Settings, on_progress: Callable[[ModelDownloadProgress], None]
    ) -> None:
        nonlocal hotkey, runtime_started
        descriptor = model_by_id(updated_settings.model_id)
        ModelInstaller(paths.model_directory).install(descriptor, on_progress)
        if runtime_started:
            return
        try:
            hotkey = start_runtime(updated_settings, model_verified=True)
        except (RuntimeError, StartupPrerequisiteError) as error:
            tray.fail_startup(error)
            raise
        runtime_started = True
        tray.activate_hotkey(hotkey)

    tray.set_model_onboarding(
        SUPPORTED_MODELS,
        lambda descriptor: model_available(descriptor.id),
        download_model,
    )

    try:
        hotkey = start_runtime(settings)
    except (RuntimeError, StartupPrerequisiteError) as error:
        if not model_available(settings.model_id):
            tray.model_setup_required()
            if not cuda_available(settings.model_id):
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
