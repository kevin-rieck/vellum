from __future__ import annotations

import builtins
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from vellum.runtime import FasterWhisperTranscriptionEngine, WindowsPrerequisiteProbe
from vellum.startup import StartupPrerequisiteError


def test_engine_registers_the_cuda_bin_directory_before_loading_cublas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cuda_bin_directory = tmp_path / "CUDA" / "v12.9" / "bin"
    cuda_bin_directory.mkdir(parents=True)
    (cuda_bin_directory / "cublas64_12.dll").touch()
    monkeypatch.setenv("CUDA_PATH", str(cuda_bin_directory.parent))
    added_directories: list[str] = []
    add_dll_directory = os.add_dll_directory

    def record_dll_directory(directory: str) -> object:
        added_directories.append(directory)
        return add_dll_directory(directory)

    monkeypatch.setattr(os, "add_dll_directory", record_dll_directory)

    class InferenceModel:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def transcribe(self, *_: object, **__: object) -> tuple[Iterator[object], object]:
            return iter(()), object()

    import_module = builtins.__import__

    def load_faster_whisper(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "faster_whisper":
            assert str(cuda_bin_directory) in added_directories
            return SimpleNamespace(WhisperModel=InferenceModel)
        return import_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", load_faster_whisper)

    FasterWhisperTranscriptionEngine(Path("large-v3-turbo"), vocabulary_hints=("Vellum",))


def test_cuda_preflight_registers_the_cuda_bin_directory_before_loading_ctranslate2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cuda_bin_directory = tmp_path / "CUDA" / "v12.9" / "bin"
    cuda_bin_directory.mkdir(parents=True)
    (cuda_bin_directory / "cublas64_12.dll").touch()
    monkeypatch.setenv("CUDA_PATH", str(cuda_bin_directory.parent))
    added_directories: list[str] = []
    add_dll_directory = os.add_dll_directory

    def record_dll_directory(directory: str) -> object:
        added_directories.append(directory)
        return add_dll_directory(directory)

    monkeypatch.setattr(os, "add_dll_directory", record_dll_directory)
    import_module = builtins.__import__

    def load_ctranslate2(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "ctranslate2":
            assert str(cuda_bin_directory) in added_directories
            return SimpleNamespace(get_cuda_device_count=lambda: 1)
        return import_module(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", load_ctranslate2)

    assert WindowsPrerequisiteProbe(Path("large-v3-turbo")).cuda_available is True


def test_cuda_preflight_registers_the_default_cuda_12_bin_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cuda_bin_directory = tmp_path / "NVIDIA GPU Computing Toolkit" / "CUDA" / "v12.9" / "bin"
    cuda_bin_directory.mkdir(parents=True)
    (cuda_bin_directory / "cublas64_12.dll").touch()
    monkeypatch.delenv("CUDA_PATH", raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("PATH", "")
    added_directories: list[str] = []
    add_dll_directory = os.add_dll_directory

    def record_dll_directory(directory: str) -> object:
        added_directories.append(directory)
        return add_dll_directory(directory)

    monkeypatch.setattr(os, "add_dll_directory", record_dll_directory)
    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        SimpleNamespace(get_cuda_device_count=lambda: 1),
    )

    assert WindowsPrerequisiteProbe(Path("large-v3-turbo")).cuda_available is True
    assert str(cuda_bin_directory) in added_directories


def test_engine_rejects_a_cuda_runtime_that_fails_on_lazy_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inference_error = RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

    class LazyInferenceFailureModel:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def transcribe(self, *_: object, **__: object) -> tuple[Iterator[object], object]:
            def segments() -> Iterator[object]:
                raise inference_error
                yield object()

            return segments(), object()

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=LazyInferenceFailureModel),
    )

    with pytest.raises(StartupPrerequisiteError) as raised:
        FasterWhisperTranscriptionEngine(Path("large-v3-turbo"), vocabulary_hints=("Vellum",))

    assert raised.value.__cause__ is inference_error


def test_engine_prerequisite_requires_all_files_in_the_selected_engine_manifest(
    tmp_path: Path,
) -> None:
    engine_directory = tmp_path / "large-v3-turbo"
    engine_directory.mkdir()
    for file_name in ("model.bin", "config.json", "tokenizer.json"):
        (engine_directory / file_name).touch()
    probe = WindowsPrerequisiteProbe(engine_directory)

    assert probe.engine_available is False

    for file_name in ("preprocessor_config.json", "vocabulary.json"):
        (engine_directory / file_name).touch()

    assert probe.engine_available is True


def test_engine_prerequisite_rejects_a_different_local_engine(tmp_path: Path) -> None:
    engine_directory = tmp_path / "small"
    engine_directory.mkdir()
    for file_name in ("model.bin", "config.json", "tokenizer.json"):
        (engine_directory / file_name).touch()

    assert WindowsPrerequisiteProbe(engine_directory).engine_available is False
