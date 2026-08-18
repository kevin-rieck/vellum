"""Explicit acquisition and verification of Vellum's local Transcription engine."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ModelError(RuntimeError):
    """Base class for failures while acquiring a local Transcription engine."""


class ModelDownloadError(ModelError):
    """The explicitly requested model download could not complete."""


class ModelVerificationError(ModelError):
    """Downloaded model files do not match Vellum's pinned model manifest."""


class ModelInstallationError(ModelError):
    """A verified model could not be atomically made available to Vellum."""


@dataclass(frozen=True, slots=True)
class ModelFile:
    """A pinned model artifact that must be present before it can be selected."""

    name: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        path = PurePosixPath(self.name)
        if not self.name or path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise ValueError("A model artifact name must be one safe file name.")
        if self.size_bytes < 0:
            raise ValueError("A model artifact size cannot be negative.")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("A model artifact SHA-256 must be a lowercase 64-character digest.")


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """A selectable, immutable source and manifest for one local model."""

    id: str
    display_name: str
    repository: str
    revision: str
    directory_name: str
    files: tuple[ModelFile, ...]

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip() for value in (self.id, self.display_name)
        ):
            raise ValueError("A model needs a stable ID and display name.")
        if self.repository.count("/") != 1 or any(not part for part in self.repository.split("/")):
            raise ValueError("A model repository must be an owner/name Hugging Face repository.")
        if len(self.revision) != 40 or any(
            character not in "0123456789abcdef" for character in self.revision
        ):
            raise ValueError("A model revision must be a pinned Git revision.")
        if PurePosixPath(self.directory_name).name != self.directory_name:
            raise ValueError("A model directory name must not contain a path.")
        if not self.files:
            raise ValueError("A model manifest must contain at least one artifact.")
        if len({model_file.name for model_file in self.files}) != len(self.files):
            raise ValueError("A model manifest cannot contain duplicate artifact names.")

    @property
    def source_url(self) -> str:
        """Return the immutable, user-visible source for this model."""
        return f"https://huggingface.co/{self.repository}/tree/{self.revision}"

    @property
    def download_size_bytes(self) -> int:
        """Return the total number of artifact bytes that Vellum will download."""
        return sum(model_file.size_bytes for model_file in self.files)


@dataclass(frozen=True, slots=True)
class ModelDownloadProgress:
    """The visible progress of one explicit model acquisition."""

    downloaded_bytes: int
    total_bytes: int
    current_file: str

    @property
    def percentage(self) -> int:
        if self.total_bytes == 0:
            return 100
        return min(100, self.downloaded_bytes * 100 // self.total_bytes)


class ModelDownloadClient(Protocol):
    """The narrow download seam used by the verified installer."""

    def download(
        self,
        descriptor: ModelDescriptor,
        model_file: ModelFile,
        destination: Path,
        on_progress: Callable[[int], None],
    ) -> None: ...


class ModelDownloader:
    """Downloads pinned model artifacts from their public Hugging Face source."""

    _CHUNK_SIZE = 1024 * 1024

    def download(
        self,
        descriptor: ModelDescriptor,
        model_file: ModelFile,
        destination: Path,
        on_progress: Callable[[int], None],
    ) -> None:
        """Download one file and report its received byte count as it streams."""
        source_url = (
            f"https://huggingface.co/{descriptor.repository}/resolve/{descriptor.revision}/"
            f"{quote(model_file.name)}"
        )
        downloaded_bytes = 0
        try:
            request = Request(source_url, headers={"User-Agent": "Vellum model downloader"})
            with urlopen(request, timeout=60) as response, destination.open("wb") as output:
                while chunk := response.read(self._CHUNK_SIZE):
                    output.write(chunk)
                    downloaded_bytes += len(chunk)
                    on_progress(downloaded_bytes)
        except (HTTPError, URLError, OSError) as error:
            raise ModelDownloadError(
                f"Vellum could not download {model_file.name} from {descriptor.source_url}: {error}"
            ) from error


class ModelVerifier:
    """Verifies every artifact against the model's pinned SHA-256 manifest."""

    _CHUNK_SIZE = 1024 * 1024

    def verify(self, descriptor: ModelDescriptor, model_directory: Path) -> None:
        """Raise a descriptive error unless every expected local artifact is exact."""
        for model_file in descriptor.files:
            file_path = model_directory / model_file.name
            if not file_path.is_file():
                raise ModelVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: "
                    f"{model_file.name} is missing."
                )
            try:
                actual_size = file_path.stat().st_size
            except OSError as error:
                raise ModelVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: "
                    f"could not read {model_file.name}."
                ) from error
            if actual_size != model_file.size_bytes:
                raise ModelVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: {model_file.name} has "
                    f"{actual_size} bytes; expected {model_file.size_bytes}."
                )

            digest = hashlib.sha256()
            try:
                with file_path.open("rb") as artifact:
                    while chunk := artifact.read(self._CHUNK_SIZE):
                        digest.update(chunk)
            except OSError as error:
                raise ModelVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: "
                    f"could not read {model_file.name}."
                ) from error
            if digest.hexdigest() != model_file.sha256:
                raise ModelVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: {model_file.name} failed "
                    "its SHA-256 check."
                )


class ModelInstaller:
    """Stages, verifies, and atomically installs only an explicitly selected model."""

    def __init__(
        self,
        destination: Path,
        *,
        downloader: ModelDownloadClient | None = None,
        verifier: ModelVerifier | None = None,
    ) -> None:
        self._destination = destination
        self._downloader = downloader or ModelDownloader()
        self._verifier = verifier or ModelVerifier()

    def install(
        self,
        descriptor: ModelDescriptor,
        on_progress: Callable[[ModelDownloadProgress], None],
    ) -> None:
        """Download, verify, and promote a model without exposing partial artifacts."""
        if self._destination.name != descriptor.directory_name:
            raise ModelInstallationError(
                f"Vellum installs {descriptor.display_name} at a directory named "
                f"{descriptor.directory_name}."
            )

        try:
            self._verifier.verify(descriptor, self._destination)
        except ModelVerificationError:
            pass
        else:
            on_progress(
                ModelDownloadProgress(
                    descriptor.download_size_bytes,
                    descriptor.download_size_bytes,
                    "Verified download",
                )
            )
            return

        try:
            self._destination.parent.mkdir(parents=True, exist_ok=True)
            staging_directory = Path(
                tempfile.mkdtemp(
                    prefix=f".{descriptor.directory_name}.download-",
                    dir=self._destination.parent,
                )
            )
        except OSError as error:
            raise ModelInstallationError(
                f"Vellum could not prepare {self._destination.parent} for a model download: {error}"
            ) from error

        try:
            downloaded_before_file = 0
            on_progress(
                ModelDownloadProgress(0, descriptor.download_size_bytes, "Preparing download")
            )
            for model_file in descriptor.files:
                destination = staging_directory / model_file.name

                def report_file_progress(
                    downloaded_bytes: int, *, file: ModelFile = model_file
                ) -> None:
                    on_progress(
                        ModelDownloadProgress(
                            downloaded_before_file + min(downloaded_bytes, file.size_bytes),
                            descriptor.download_size_bytes,
                            file.name,
                        )
                    )

                self._downloader.download(descriptor, model_file, destination, report_file_progress)
                downloaded_before_file += model_file.size_bytes
                on_progress(
                    ModelDownloadProgress(
                        downloaded_before_file, descriptor.download_size_bytes, model_file.name
                    )
                )

            self._verifier.verify(descriptor, staging_directory)
            self._promote(staging_directory)
            on_progress(
                ModelDownloadProgress(
                    descriptor.download_size_bytes,
                    descriptor.download_size_bytes,
                    "Verified download",
                )
            )
        finally:
            if staging_directory.exists():
                shutil.rmtree(staging_directory, ignore_errors=True)

    def _promote(self, staging_directory: Path) -> None:
        """Atomically replace an incomplete previous directory only after verification."""
        backup_directory: Path | None = None
        try:
            if self._destination.exists():
                backup_directory = self._destination.with_name(
                    f".{self._destination.name}.previous-{uuid.uuid4().hex}"
                )
                self._destination.replace(backup_directory)
            staging_directory.replace(self._destination)
        except OSError as error:
            if (
                backup_directory is not None
                and backup_directory.exists()
                and not self._destination.exists()
            ):
                try:
                    backup_directory.replace(self._destination)
                except OSError:
                    pass
            raise ModelInstallationError(
                f"Vellum verified the model but could not install it at "
                f"{self._destination}: {error}"
            ) from error
        else:
            if backup_directory is not None:
                shutil.rmtree(backup_directory, ignore_errors=True)


def format_download_size(size_bytes: int) -> str:
    """Format a model's exact declared size for the Settings window."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KiB"
    if size_bytes < 1024**3:
        return f"{size_bytes / 1024**2:.1f} MiB"
    return f"{size_bytes / 1024**3:.2f} GiB"


LARGE_V3_TURBO = ModelDescriptor(
    id="large-v3-turbo",
    display_name="large-v3-turbo",
    repository="deepdml/faster-whisper-large-v3-turbo-ct2",
    revision="4df90f75321148c3a29a9e2351b7ddf8f5b115a8",
    directory_name="large-v3-turbo",
    files=(
        ModelFile(
            "config.json",
            2_263,
            "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e",
        ),
        ModelFile(
            "model.bin",
            1_617_884_929,
            "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da",
        ),
        ModelFile(
            "preprocessor_config.json",
            340,
            "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711",
        ),
        ModelFile(
            "tokenizer.json",
            2_710_337,
            "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd",
        ),
        ModelFile(
            "vocabulary.json",
            1_068_114,
            "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1",
        ),
    ),
)

SUPPORTED_MODELS = (LARGE_V3_TURBO,)


def model_by_id(model_id: str) -> ModelDescriptor:
    """Return the selectable model identified by a persisted settings value."""
    for descriptor in SUPPORTED_MODELS:
        if descriptor.id == model_id:
            return descriptor
    raise ValueError(f"Vellum does not support the model {model_id!r}.")
