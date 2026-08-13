from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from vellum.runtime import FasterWhisperTranscriptionEngine, SoundDeviceRecorder


class AccessDeniedError(Exception):
    pass


class OneDimensionalAudioModel:
    def __init__(self) -> None:
        self.transcription_options: dict[str, object] = {}

    def transcribe(self, audio: object, **kwargs: object) -> tuple[object, object]:
        assert getattr(audio, "ndim") == 1, "Input should be a 1D array"
        self.transcription_options = kwargs
        return iter(()), object()


class CapturingInputStream:
    instance: CapturingInputStream | None = None

    def __init__(self, **kwargs: object) -> None:
        callback = kwargs["callback"]
        assert callable(callback)
        self.callback = callback
        CapturingInputStream.instance = self

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


def test_recorder_output_can_be_transcribed_by_vad_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(InputStream=CapturingInputStream, PortAudioError=Exception),
    )
    recorder = SoundDeviceRecorder()
    recorder.start()
    assert CapturingInputStream.instance is not None
    CapturingInputStream.instance.callback(
        np.array([[0.1], [0.2]], dtype=np.float32), 2, None, None
    )

    engine = FasterWhisperTranscriptionEngine.__new__(FasterWhisperTranscriptionEngine)
    engine._model = OneDimensionalAudioModel()
    engine._hotwords = "Vellum, CTranslate2"

    assert engine.transcribe(recorder.stop()) == ""
    assert engine._model.transcription_options["hotwords"] == "Vellum, CTranslate2"


def test_recorder_limits_retained_audio_to_its_configured_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import numpy as np

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(InputStream=CapturingInputStream, PortAudioError=Exception),
    )
    recorder = SoundDeviceRecorder(sample_rate=2, maximum_seconds=1)
    recorder.start()
    assert CapturingInputStream.instance is not None
    CapturingInputStream.instance.callback(
        np.array([[0.1], [0.2], [0.3]], dtype=np.float32), 3, None, None
    )
    CapturingInputStream.instance.callback(np.array([[0.4]], dtype=np.float32), 1, None, None)

    assert np.array_equal(recorder.stop(), np.array([0.1, 0.2], dtype=np.float32))


@pytest.mark.parametrize("failure", ["stop", "close"])
def test_recorder_releases_audio_when_stream_shutdown_fails(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    class FailingInputStream(CapturingInputStream):
        def stop(self) -> None:
            if failure == "stop":
                raise RuntimeError("stop failed")

        def close(self) -> None:
            if failure == "close":
                raise RuntimeError("close failed")

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(InputStream=FailingInputStream, PortAudioError=Exception),
    )
    recorder = SoundDeviceRecorder()
    recorder.start()

    with pytest.raises(RuntimeError, match=f"{failure} failed"):
        recorder.stop()

    assert recorder._stream is None
    assert recorder._chunks == []


def test_recorder_explains_how_to_grant_windows_microphone_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_access(**_: object) -> object:
        raise AccessDeniedError("MME error 1")

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(InputStream=deny_access, PortAudioError=AccessDeniedError),
    )

    with pytest.raises(RuntimeError, match="Let desktop apps access your microphone"):
        SoundDeviceRecorder().start()
