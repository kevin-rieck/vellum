# Vellum v1 release acceptance

This checklist validates the installed Windows distribution. It is intentionally separate
from the source-checkout tracer bullet and does not require `uv`.

## Prerequisites

- Windows 10 or newer, an NVIDIA CUDA-capable GPU, and the CUDA 12 runtime with
  `cublas64_12.dll` available to CTranslate2.
- A working microphone and Notepad (or another non-elevated application that accepts
  Ctrl+V).
- The versioned `Vellum-<version>-setup.exe` release artifact.

## Setup and first launch

1. Run the installer as the current user. Confirm that it completes without an elevation
   prompt and creates the Vellum Start menu shortcut.
2. Launch Vellum and confirm that a blue Vellum icon appears in the system tray.
3. Open **Settings**. Confirm that the selected engine identifies
   `deepdml/faster-whisper-large-v3-turbo-ct2`, its pinned source, and its declared size.
4. Select **Download and verify Transcription engine**. Confirm byte progress is shown and
   that the control reports a verified local installation.
5. Close and relaunch Vellum. Confirm that startup warms the local engine without another
   engine download or a cloud request. The tray becomes ready after warm-up.

## Text insertion safety

1. Focus Notepad, hold the configured Activation hotkey (default `Ctrl+Alt+Space`), speak
   English, and release the hotkey.
2. Confirm the tray indicates recording and then transcribing, and that the raw Transcript
   is pasted into the same Notepad window.
3. Press Ctrl+V again and confirm the Transcript remains in the clipboard.
4. Start another Dictation session and move focus to a different window before
   transcription completes. Confirm no paste occurs and that the Transcript remains in the
   clipboard with a cancellation notification.
5. Confirm that a session containing no usable speech leaves the pre-existing clipboard
   untouched and displays a No-speech notification.
6. Hold the Activation hotkey for 60 seconds. Confirm capture ends at the limit and that a
   second activation cannot overlap the in-progress Transcription.
7. Focus an elevated application and run a session. Confirm no unsafe Ctrl+V is injected;
   the Transcript remains available in the clipboard and the user receives an error.

## Privacy and release services

1. In **Settings**, choose **Copy redacted diagnostics**. Confirm the clipboard contains
   product/runtime context and sanitized error categories only. It must not contain audio,
   Transcripts, clipboard contents, Settings values, exception messages, or user paths.
2. Confirm no diagnostic file is sent anywhere. Vellum has no automatic diagnostics upload,
   telemetry, or startup update request.
3. Choose **Check for updates**. Confirm that it is the only action that contacts the
   configured HTTPS release metadata endpoint. An available release displays its HTTPS
   release link; Vellum does not download or install it automatically.
4. Select **Quit**, uninstall from Windows Apps, and confirm that the installed executable
   is removed while `%LOCALAPPDATA%\Vellum` retains Settings, the verified engine, and the
   local diagnostics log.

## Automated release gates

From a development checkout, run:

```powershell
uv sync --locked --all-groups
uv run pytest
uv run mypy src
uv run ruff check .
```

The Windows packaging job additionally builds the PyInstaller executable and Inno Setup
installer. The engine remains a separately verified first-run download.
