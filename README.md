# Vellum

Vellum is a Windows-first, local-only Push-to-talk dictation application. Hold
**Ctrl+Alt+Space**, speak, and release it to transcribe with the local
`large-v3-turbo` Transcription engine. Vellum copies the resulting English Transcript to the
system clipboard and sends Ctrl+V only if the foreground Insertion target is
the same window that was focused when microphone capture ended.

## Installed Windows release

Download the versioned `Vellum-<version>-setup.exe` from the project's release page and
run it as the current Windows user. The installer creates a Start menu shortcut and can
optionally create a desktop shortcut; it does not require administrator access. It does
not bundle the approximately 1.51 GiB Transcription engine. The engine is acquired
explicitly and verified from Settings on first launch.

The installer keeps `%LOCALAPPDATA%\\Vellum\\settings.json`, the verified engine, and the
redacted local diagnostics log when the application is uninstalled. Reinstalling Vellum
therefore preserves the user's Settings and downloaded engine.

## Tracer-bullet setup

Install [uv](https://docs.astral.sh/uv/) first. It provisions the project-pinned
Python 3.13 environment and installs the versions recorded in `uv.lock`.

Vellum requires Windows, an NVIDIA CUDA-capable GPU available to CTranslate2,
and the CUDA 12 runtime (including `cublas64_12.dll`). Install a compatible
NVIDIA CUDA 12 toolkit and ensure its `bin` directory is on `PATH`; the NVIDIA
driver alone does not provide the cuBLAS runtime DLL.

```powershell
uv sync --locked
uv run vellum
```

On first launch, open the tray **Settings** window and explicitly choose
**Download and verify Transcription engine**. It identifies the pinned Hugging Face source
([`deepdml/faster-whisper-large-v3-turbo-ct2`](https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2)),
its 1.51 GiB download size, and byte progress. Vellum writes the engine artifacts
to a staging directory, verifies every downloaded file against its pinned SHA-256
manifest, then atomically installs them at
`%LOCALAPPDATA%\Vellum\engines\large-v3-turbo`. A failed or corrupt download is
never selectable. After verification Vellum warms the selected local
Transcription engine and keeps it resident. Normal startup verifies the local
manifest and Dictation sessions use only local files; they make no
engine-download or cloud-inference requests.

The selected Transcription engine and additional Vocabulary hints are persisted in
`%LOCALAPPDATA%\Vellum\settings.json`. Enter one term per line (or
comma-separated) in Settings; Vellum always also supplies its own name to the
Transcription engine. Hints are passed directly to transcription, not used for
post-transcription replacements. Set `VELLUM_ENGINE_DIR` only to use an existing
local `large-v3-turbo` directory (the directory name must remain
`large-v3-turbo`).

To verify the installed release, follow the [v1 acceptance checklist](docs/release/v1-acceptance.md).
In brief, open Settings and explicitly download and verify the Transcription engine, then
focus Notepad, hold Ctrl+Alt+Space while speaking English, and release it. The raw
Transcript should appear in Notepad and remain available through Ctrl+V. The tray's
**Settings** command can select the Transcription engine and its Vocabulary hints, select
an Input device, change the Activation hotkey, toggle sounds, opt in to start-at-sign-in,
check for updates, and copy redacted diagnostics. These choices are stored in
`%LOCALAPPDATA%\Vellum\settings.json`. Update discovery is user-initiated and only
provides a release link; Vellum never downloads or installs an update automatically.
Vellum keeps using the Windows default Input device until one is selected, and
reports an unavailable selected device instead of switching microphones. If
focus moves while the Transcription engine processes the Dictation session,
Vellum does not paste and instead notifies you that the Transcript remains in
the clipboard. Errors are written locally to `%LOCALAPPDATA%\Vellum\vellum.log`
using an allowlist of exception types and sanitized stack locations. The log never
contains exception messages, user paths, audio, Transcripts, clipboard contents, or
Settings values. **Settings > Copy redacted diagnostics** places a sanitized snapshot
in the clipboard only after the user requests it; Vellum has no diagnostics upload or
telemetry path.

## License

Vellum is distributed under the [Apache License 2.0](LICENSE).

## Development

The agreed verification seams are startup prerequisite validation and the
`DictationSession` lifecycle (capture-end Insertion target identification through
Text insertion). They are deliberately platform-independent; the Windows
adapters are kept behind those seams.

```powershell
uv sync --locked --all-groups
uv run pytest tests/test_startup.py
uv run pytest tests/test_dictation_session.py
uv run mypy src
uv run ruff check .
uv run pytest
```
