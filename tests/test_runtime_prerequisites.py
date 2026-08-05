from __future__ import annotations

from pathlib import Path

from vellum.runtime import WindowsPrerequisiteProbe


def test_model_prerequisite_requires_all_files_needed_by_the_local_engine(tmp_path: Path) -> None:
    model_directory = tmp_path / "large-v3-turbo"
    model_directory.mkdir()
    (model_directory / "model.bin").touch()
    probe = WindowsPrerequisiteProbe(model_directory)

    assert probe.model_available is False

    (model_directory / "config.json").touch()
    (model_directory / "tokenizer.json").touch()

    assert probe.model_available is True


def test_model_prerequisite_rejects_a_different_local_model(tmp_path: Path) -> None:
    model_directory = tmp_path / "small"
    model_directory.mkdir()
    for file_name in ("model.bin", "config.json", "tokenizer.json"):
        (model_directory / file_name).touch()

    assert WindowsPrerequisiteProbe(model_directory).model_available is False
