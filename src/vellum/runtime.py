"""Local CUDA transcription and microphone capture adapters."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING, Any

from vellum.startup import StartupPrerequisiteError

if TYPE_CHECKING:
    import numpy as np


class WindowsPrerequisiteProbe:
    """Checks runtime prerequisites without downloading models or contacting a service."""

    def __init__(self, model_directory: Path) -> None:
        self._model_directory = model_directory

    @property
    def model_directory(self) -> Path:
        return self._model_directory

    @property
    def model_available(self) -> bool:
        # The path name is an intentional v1 guard against silently using another model.
        if self.model_directory.name != "large-v3-turbo":
            return False
        required_files = ("model.bin", "config.json", "tokenizer.json")
        return all((self.model_directory / file_name).is_file() for file_name in required_files)

    @property
    def cuda_available(self) -> bool:
        try:
            import ctranslate2
        except ImportError:
            return False
        return int(ctranslate2.get_cuda_device_count()) > 0


class FasterWhisperTranscriptionEngine:
    """The resident local Transcription engine required by the v1 domain model."""

    def __init__(self, model_directory: Path) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise StartupPrerequisiteError(
                "Vellum cannot start; install the local faster-whisper runtime."
            ) from error

        try:
            self._model: Any = WhisperModel(
                str(model_directory), device="cuda", compute_type="float16", local_files_only=True
            )
        except Exception as error:
            raise StartupPrerequisiteError(
                "Vellum cannot start; the local large-v3-turbo model could not be loaded on CUDA."
            ) from error

    def transcribe(self, audio: object) -> str:
        segments, _ = self._model.transcribe(
            audio,
            language="en",
            vad_filter=True,
            condition_on_previous_text=False,
        )
        return "".join(segment.text for segment in segments)


class AsyncFasterWhisperTranscriptionEngine:
    """Warms the resident Transcription engine without delaying the tray startup."""

    def __init__(self, model_directory: Path, on_ready: Callable[[Exception | None], None]) -> None:
        self._ready = Event()
        self._engine: FasterWhisperTranscriptionEngine | None = None
        self._error: Exception | None = None
        self._on_ready = on_ready
        self._model_directory = model_directory
        self._warming_started = False

    def start_warming(self) -> None:
        """Begin warm-up after the tray and disabled hotkey have been constructed."""
        if self._warming_started:
            return
        self._warming_started = True
        Thread(target=self._warm, args=(self._model_directory,), daemon=True).start()

    def wait_until_ready(self) -> None:
        """Raise the warm-up error during startup, before the hotkey is enabled."""
        if not self._warming_started:
            raise RuntimeError("The local Transcription engine has not started warming.")
        self._ready.wait()
        if self._error is not None:
            raise self._error
        if self._engine is None:
            raise RuntimeError("The local Transcription engine did not finish warming.")

    def transcribe(self, audio: object) -> str:
        self.wait_until_ready()
        if self._engine is None:
            raise RuntimeError("The local Transcription engine did not finish warming.")
        return self._engine.transcribe(audio)

    def _warm(self, model_directory: Path) -> None:
        try:
            self._engine = FasterWhisperTranscriptionEngine(model_directory)
        except Exception as error:
            self._error = error
            self._on_ready(error)
        else:
            self._on_ready(None)
        finally:
            self._ready.set()


class SoundDeviceRecorder:
    """Captures one in-memory microphone stream, limited to 60 seconds."""

    def __init__(self, *, sample_rate: int = 16_000, maximum_seconds: int = 60) -> None:
        self._sample_rate = sample_rate
        self._maximum_frames = sample_rate * maximum_seconds
        self._chunks: list[np.ndarray[Any, Any]] = []
        self._lock = Lock()
        self._stream: Any | None = None

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as error:
            raise RuntimeError("The sounddevice microphone runtime is not installed.") from error

        with self._lock:
            self._chunks = []

        def capture(
            indata: np.ndarray[Any, Any], frames: int, time: object, status: object
        ) -> None:
            del frames, time
            if status:
                return
            with self._lock:
                captured_frames = sum(len(chunk) for chunk in self._chunks)
                remaining_frames = self._maximum_frames - captured_frames
                if remaining_frames > 0:
                    self._chunks.append(indata[:remaining_frames].copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                callback=capture,
            )
            self._stream.start()
        except sd.PortAudioError as error:
            self._stream = None
            raise RuntimeError(
                "Vellum could not access the microphone. In Windows Settings > Privacy & "
                "security > Microphone, turn on Microphone access and Let desktop apps "
                "access your microphone, then restart Vellum."
            ) from error

    def stop(self) -> np.ndarray[Any, Any]:
        if self._stream is None:
            raise RuntimeError("No microphone capture is active.")
        self._stream.stop()
        self._stream.close()
        self._stream = None

        import numpy as np

        with self._lock:
            chunks: Sequence[np.ndarray[Any, Any]] = self._chunks
            self._chunks = []
        if not chunks:
            return np.empty((0, 1), dtype=np.float32)
        return np.concatenate(chunks, axis=0)
