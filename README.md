# Vellum

Vellum is a Windows-first, local-only Push-to-talk dictation application. Hold
**Ctrl+Alt+Space**, speak, and release it to transcribe with the local
`large-v3-turbo` model. Vellum copies the resulting English Transcript to the
system clipboard and sends Ctrl+V only if the foreground Insertion target is
the same window that was focused when microphone capture ended.

## Tracer-bullet setup

Install [uv](https://docs.astral.sh/uv/) first. It provisions the project-pinned
Python 3.13 environment and installs the versions recorded in `uv.lock`.

Vellum requires Windows, an NVIDIA CUDA-capable GPU available to CTranslate2,
the CUDA 12 runtime (including `cublas64_12.dll`), and a pre-downloaded
CTranslate2 `large-v3-turbo` model. Install a compatible NVIDIA CUDA 12 toolkit
and ensure its `bin` directory is on `PATH`; the NVIDIA driver alone does not
provide the cuBLAS runtime DLL. It never downloads a model or sends Dictation
session data at runtime.

```powershell
uv sync --locked --extra model-download
uv run hf download deepdml/faster-whisper-large-v3-turbo-ct2 `
  --local-dir "$env:LOCALAPPDATA\Vellum\models\large-v3-turbo"
uv run vellum
```

Set `VELLUM_MODEL_DIR` to use another local `large-v3-turbo` model directory
(the directory name must remain `large-v3-turbo`). Set `VELLUM_VOCABULARY_HINTS`
to a comma-separated list of local Vocabulary hints for names or domain terms
(for example, `Vellum, CTranslate2`). Vellum always includes its own name as a
Vocabulary hint. On startup Vellum checks CUDA availability and the local model
files, and reports every missing or unloadable prerequisite before it enables
Push-to-talk.

To verify the tracer bullet, focus Notepad, hold Ctrl+Alt+Space while speaking
English, then release it. The raw Transcript should appear in Notepad and
remain available through Ctrl+V. The tray's **Settings** command can select an
Input device, change the Activation hotkey, toggle sounds, and opt in to
start-at-sign-in; these choices are stored in `%LOCALAPPDATA%\Vellum\settings.json`.
Vellum keeps using the Windows default Input device until one is selected, and
reports an unavailable selected device instead of switching microphones. If
focus moves while the Transcription engine processes the Dictation session,
Vellum does not paste and instead notifies you that the Transcript remains in
the clipboard. Errors are also written to the launching console and to
`%LOCALAPPDATA%\Vellum\vellum.log`, including a traceback for failures after
the hotkey is used. The log never contains audio or Transcripts.

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
