from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

import pytest

from vellum.models import (
    ModelDescriptor,
    ModelDownloadProgress,
    ModelFile,
    ModelInstaller,
    ModelVerificationError,
    ModelVerifier,
)


class FakeDownloader:
    def __init__(self, contents: dict[str, bytes]) -> None:
        self.contents = contents
        self.sources: list[str] = []

    def download(
        self,
        descriptor: ModelDescriptor,
        model_file: ModelFile,
        destination: Path,
        on_progress: Callable[[int], None],
    ) -> None:
        self.sources.append(descriptor.source_url)
        contents = self.contents[model_file.name]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)
        on_progress(len(contents))


def descriptor_for(contents: dict[str, bytes]) -> ModelDescriptor:
    return ModelDescriptor(
        id="test-model",
        display_name="Test model",
        repository="vellum/test-model",
        revision="0123456789abcdef0123456789abcdef01234567",
        directory_name="test-model",
        files=tuple(
            ModelFile(name, len(content), sha256(content).hexdigest())
            for name, content in contents.items()
        ),
    )


def test_installer_reports_source_and_byte_progress_then_promotes_a_verified_model(
    tmp_path: Path,
) -> None:
    contents = {"model.bin": b"model", "config.json": b"config"}
    descriptor = descriptor_for(contents)
    downloader = FakeDownloader(contents)
    progress: list[ModelDownloadProgress] = []
    destination = tmp_path / "models" / descriptor.directory_name

    ModelInstaller(destination, downloader=downloader).install(descriptor, progress.append)

    assert downloader.sources == [descriptor.source_url, descriptor.source_url]
    assert destination.joinpath("model.bin").read_bytes() == b"model"
    assert destination.joinpath("config.json").read_bytes() == b"config"
    assert progress[0].downloaded_bytes == 0
    assert progress[-1] == ModelDownloadProgress(
        downloaded_bytes=descriptor.download_size_bytes,
        total_bytes=descriptor.download_size_bytes,
        current_file="Verified download",
    )


def test_verifier_rejects_a_same_size_corrupt_selected_model(tmp_path: Path) -> None:
    descriptor = descriptor_for({"model.bin": b"expected"})
    model_directory = tmp_path / descriptor.directory_name
    model_directory.mkdir()
    (model_directory / "model.bin").write_bytes(b"corrupt!")

    with pytest.raises(ModelVerificationError, match="SHA-256"):
        ModelVerifier().verify(descriptor, model_directory)


def test_installer_does_not_promote_a_corrupt_download(tmp_path: Path) -> None:
    expected_contents = {"model.bin": b"expected"}
    descriptor = descriptor_for(expected_contents)
    destination = tmp_path / "models" / descriptor.directory_name

    with pytest.raises(ModelVerificationError, match="model.bin"):
        ModelInstaller(destination, downloader=FakeDownloader({"model.bin": b"corrupt"})).install(
            descriptor, lambda _: None
        )

    assert not destination.exists()
    assert list(destination.parent.glob(f".{descriptor.directory_name}.download-*")) == []
