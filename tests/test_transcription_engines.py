from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

import pytest

from vellum.transcription_engines import (
    EngineArtifact,
    EngineDownloadProgress,
    EngineInstaller,
    EngineVerifier,
    TranscriptionEngineDescriptor,
    TranscriptionEngineId,
    TranscriptionEngineVerificationError,
)


class FakeDownloader:
    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents
        self.sources: list[str] = []

    def download(
        self,
        descriptor: TranscriptionEngineDescriptor,
        artifact: EngineArtifact,
        destination: Path,
        on_progress: Callable[[int], None],
    ) -> None:
        self.sources.append(descriptor.source_url)
        contents = self.contents[artifact.name]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
        on_progress(len(contents))


def descriptor_for(contents: dict[str, bytes]) -> TranscriptionEngineDescriptor:
    return TranscriptionEngineDescriptor(
        id=TranscriptionEngineId("test-engine"),
        display_name="Test engine",
        repository="vellum/test-engine",
        revision="0123456789abcdef0123456789abcdef01234567",
        directory_name="test-engine",
        files=tuple(
            EngineArtifact(name, len(content), sha256(content).hexdigest())
            for name, content in contents.items()
        ),
    )


def test_installer_reports_source_and_byte_progress_then_promotes_a_verified_engine(
    tmp_path: Path,
) -> None:
    contents = {"model.bin": b"model", "config.json": b"config"}
    descriptor = descriptor_for(contents)
    downloader = FakeDownloader(contents)
    progress: list[EngineDownloadProgress] = []
    destination = tmp_path / "engines" / descriptor.directory_name

    EngineInstaller(destination, downloader=downloader).install(descriptor, progress.append)

    assert downloader.sources == [descriptor.source_url, descriptor.source_url]
    assert destination.joinpath("model.bin").read_bytes() == b"model"
    assert destination.joinpath("config.json").read_bytes() == b"config"
    assert progress[0].downloaded_bytes == 0
    assert progress[-1] == EngineDownloadProgress(
        downloaded_bytes=descriptor.download_size_bytes,
        total_bytes=descriptor.download_size_bytes,
        current_file="Verified download",
    )


def test_verifier_rejects_a_same_size_corrupt_selected_engine(tmp_path: Path) -> None:
    descriptor = descriptor_for({"model.bin": b"expected"})
    engine_directory = tmp_path / descriptor.directory_name
    engine_directory.mkdir()
    (engine_directory / "model.bin").write_bytes(b"corrupt!")

    with pytest.raises(TranscriptionEngineVerificationError, match="SHA-256"):
        EngineVerifier().verify(descriptor, engine_directory)


def test_installer_does_not_promote_a_corrupt_download(tmp_path: Path) -> None:
    expected_contents = {"model.bin": b"expected"}
    descriptor = descriptor_for(expected_contents)
    destination = tmp_path / "engines" / descriptor.directory_name

    with pytest.raises(TranscriptionEngineVerificationError, match="model.bin"):
        EngineInstaller(destination, downloader=FakeDownloader({"model.bin": b"corrupt"})).install(
            descriptor, lambda _: None
        )

    assert not destination.exists()
    assert list(destination.parent.glob(f".{descriptor.directory_name}.download-*")) == []
