# Vellum

Vellum is a Windows-first, local-only Push-to-talk dictation application. Hold
**Ctrl+Alt+Space**, speak, and release it to transcribe with the local
`large-v3-turbo` model. Vellum copies the resulting English Transcript to the
system clipboard and sends Ctrl+V only if the foreground Insertion target is
the same window that was focused at release.

## Tracer-bullet setup

Vellum requires Windows, an NVIDIA CUDA-capable GPU available to CTranslate2,
and a pre-downloaded CTranslate2 `large-v3-turbo` model. It never downloads a
model or sends Dictation session data at runtime.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install huggingface_hub
huggingface-cli download Systran/faster-whisper-large-v3-turbo `
  --local-dir "$env:LOCALAPPDATA\Vellum\models\large-v3-turbo"
vellum
```

Set `VELLUM_MODEL_DIR` to use another local `large-v3-turbo` model directory
(the directory name must remain `large-v3-turbo`). On startup Vellum checks
CUDA availability and the local model files, and reports every missing or
unloadable prerequisite before it enables Push-to-talk.

To verify the tracer bullet, focus Notepad, hold Ctrl+Alt+Space while speaking
English, then release it. The raw Transcript should appear in Notepad and
remain available through Ctrl+V. If focus moves while transcription runs,
Vellum does not paste and instead notifies you that the Transcript remains in
the clipboard.

## Development

The agreed verification seams are startup prerequisite validation and the
`DictationSession` lifecycle (release target capture through clipboard-backed
Text insertion). They are deliberately platform-independent; the Windows
adapters are kept behind those seams.

```powershell
pip install -e ".[dev]"
python -m pytest tests/test_startup.py
python -m pytest tests/test_dictation_session.py
python -m mypy src
python -m ruff check .
python -m pytest
```
