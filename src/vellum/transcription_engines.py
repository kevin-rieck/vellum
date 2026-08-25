"""Explicit acquisition and verification of Vellum's local Transcription engines."""

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


@dataclass(frozen=True, slots=True)
class TranscriptionEngineId:
    """The stable identifier persisted for a selectable Transcription engine."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("A Transcription engine identifier must be non-empty text.")
        object.__setattr__(self, "value", self.value.strip())

    def __str__(self) -> str:
        return self.value


class TranscriptionEngineError(RuntimeError):
    """Base class for failures while acquiring a local Transcription engine."""


class TranscriptionEngineDownloadError(TranscriptionEngineError):
    """The explicitly requested Transcription engine download could not complete."""


class TranscriptionEngineVerificationError(TranscriptionEngineError):
    """Downloaded engine artifacts do not match Vellum's pinned manifest."""


class TranscriptionEngineInstallationError(TranscriptionEngineError):
    """A verified Transcription engine could not be atomically made available to Vellum."""


@dataclass(frozen=True, slots=True)
class EngineArtifact:
    """A pinned artifact that must be present before an engine can be selected."""

    name: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        path = PurePosixPath(self.name)
        if not self.name or path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise ValueError("An engine artifact name must be one safe file name.")
        if self.size_bytes < 0:
            raise ValueError("An engine artifact size cannot be negative.")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("An engine artifact SHA-256 must be a lowercase 64-character digest.")


@dataclass(frozen=True, slots=True)
class TranscriptionEngineDescriptor:
    """A selectable, immutable source and manifest for one local Transcription engine."""

    id: TranscriptionEngineId
    display_name: str
    repository: str
    revision: str
    directory_name: str
    files: tuple[EngineArtifact, ...]

    def __post_init__(self) -> None:
        if isinstance(self.id, str):
            try:
                object.__setattr__(self, "id", TranscriptionEngineId(self.id))
            except ValueError as error:
                raise ValueError("A Transcription engine needs a stable identifier.") from error
        if not isinstance(self.id, TranscriptionEngineId):
            raise ValueError("A Transcription engine needs a stable identifier.")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("A Transcription engine needs a display name.")
        if self.repository.count("/") != 1 or any(
            not part for part in self.repository.split("/")
        ):
            raise ValueError("An engine repository must be an owner/name Hugging Face repository.")
        if len(self.revision) != 40 or any(
            character not in "0123456789abcdef" for character in self.revision
        ):
            raise ValueError("An engine revision must be a pinned Git revision.")
        if PurePosixPath(self.directory_name).name != self.directory_name:
            raise ValueError("An engine directory name must not contain a path.")
        if not self.files:
            raise ValueError("An engine manifest must contain at least one artifact.")
        if len({artifact.name for artifact in self.files}) != len(self.files):
            raise ValueError("An engine manifest cannot contain duplicate artifact names.")

    @property
    def source_url(self) -> str:
        """Return the immutable, user-visible source for this engine."""
        return f"https://huggingface.co/{self.repository}/tree/{self.revision}"

    @property
    def download_size_bytes(self) -> int:
        """Return the total number of artifact bytes that Vellum will download."""
        return sum(artifact.size_bytes for artifact in self.files)


@dataclass(frozen=True, slots=True)
class EngineDownloadProgress:
    """The visible progress of one explicit Transcription engine acquisition."""

    downloaded_bytes: int
    total_bytes: int
    current_file: str

    @property
    def percentage(self) -> int:
        if self.total_bytes == 0:
            return 100
        return min(100, self.downloaded_bytes * 100 // self.total_bytes)


class EngineDownloadClient(Protocol):
    """The narrow download seam used by the verified installer."""

    def download(
        self,
        descriptor: TranscriptionEngineDescriptor,
        artifact: EngineArtifact,
        destination: Path,
        on_progress: Callable[[int], None],
    ) -> None: ...


class EngineDownloader:
    """Downloads pinned engine artifacts from their public Hugging Face source."""

    _CHUNK_SIZE = 1024 * 1024

    def download(
        self,
        descriptor: TranscriptionEngineDescriptor,
        artifact: EngineArtifact,
        destination: Path,
        on_progress: Callable[[int], None],
    ) -> None:
        """Download one artifact and report its received byte count as it streams."""
        source_url = (
            f"https://huggingface.co/{descriptor.repository}/resolve/{descriptor.revision}/"
            f"{quote(artifact.name)}"
        )
        downloaded_bytes = 0
        try:
            request = Request(source_url, headers={"User-Agent": "Vellum engine downloader"})
            with urlopen(request, timeout=60) as response, destination.open("wb") as output:
                while chunk := response.read(self._CHUNK_SIZE):
                    output.write(chunk)
                    downloaded_bytes += len(chunk)
                    on_progress(downloaded_bytes)
        except (HTTPError, URLError, OSError) as error:
            raise TranscriptionEngineDownloadError(
                f"Vellum could not download {artifact.name} from {descriptor.source_url}: {error}"
            ) from error


class EngineVerifier:
    """Verifies every artifact against the engine's pinned SHA-256 manifest."""

    _CHUNK_SIZE = 1024 * 1024

    def verify(self, descriptor: TranscriptionEngineDescriptor, engine_directory: Path) -> None:
        """Raise a descriptive error unless every expected local artifact is exact."""
        for artifact in descriptor.files:
            file_path = engine_directory / artifact.name
            if not file_path.is_file():
                raise TranscriptionEngineVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: "
                    f"{artifact.name} is missing."
                )
            try:
                actual_size = file_path.stat().st_size
            except OSError as error:
                raise TranscriptionEngineVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: "
                    f"could not read {artifact.name}."
                ) from error
            if actual_size != artifact.size_bytes:
                raise TranscriptionEngineVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: {artifact.name} has "
                    f"{actual_size} bytes; expected {artifact.size_bytes}."
                )

            digest = hashlib.sha256()
            try:
                with file_path.open("rb") as downloaded_artifact:
                    while chunk := downloaded_artifact.read(self._CHUNK_SIZE):
                        digest.update(chunk)
            except OSError as error:
                raise TranscriptionEngineVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: "
                    f"could not read {artifact.name}."
                ) from error
            if digest.hexdigest() != artifact.sha256:
                raise TranscriptionEngineVerificationError(
                    f"Vellum could not verify {descriptor.display_name}: {artifact.name} failed "
                    "its SHA-256 check."
                )


class EngineInstaller:
    """Stages, verifies, and atomically installs an explicitly selected engine."""

    def __init__(
        self,
        destination: Path,
        *,
        downloader: EngineDownloadClient | None = None,
        verifier: EngineVerifier | None = None,
    ) -> None:
        self._destination = destination
        self._downloader = downloader or EngineDownloader()
        self._verifier = verifier or EngineVerifier()

    def install(
        self,
        descriptor: TranscriptionEngineDescriptor,
        on_progress: Callable[[EngineDownloadProgress], None],
    ) -> None:
        """Download, verify, and promote an engine without exposing partial artifacts."""
        if self._destination.name != descriptor.directory_name:
            raise TranscriptionEngineInstallationError(
                f"Vellum installs {descriptor.display_name} at a directory named "
                f"{descriptor.directory_name}."
            )

        try:
            self._verifier.verify(descriptor, self._destination)
        except TranscriptionEngineVerificationError:
            pass
        else:
            on_progress(
                EngineDownloadProgress(
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
            raise TranscriptionEngineInstallationError(
                f"Vellum could not prepare {self._destination.parent} for an engine download: "
                f"{error}"
            ) from error

        try:
            downloaded_before_file = 0
            on_progress(
                EngineDownloadProgress(0, descriptor.download_size_bytes, "Preparing download")
            )
            for artifact in descriptor.files:
                destination = staging_directory / artifact.name

                def report_file_progress(
                    downloaded_bytes: int, *, file: EngineArtifact = artifact
                ) -> None:
                    on_progress(
                        EngineDownloadProgress(
                            downloaded_before_file + min(downloaded_bytes, file.size_bytes),
                            descriptor.download_size_bytes,
                            file.name,
                        )
                    )

                self._downloader.download(descriptor, artifact, destination, report_file_progress)
                downloaded_before_file += artifact.size_bytes
                on_progress(
                    EngineDownloadProgress(
                        downloaded_before_file, descriptor.download_size_bytes, artifact.name
                    )
                )

            self._verifier.verify(descriptor, staging_directory)
            self._promote(staging_directory)
            on_progress(
                EngineDownloadProgress(
                    descriptor.download_size_bytes,
                    descriptor.download_size_bytes,
                    "Verified download",
                )
            )
        finally:
            if staging_directory.exists():
                shutil.rmtree(staging_directory, ignore_errors=True)

    def _promote(self, staging_directory: Path) -> None:
        """Atomically replace an incomplete previous directory after verification."""
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
            raise TranscriptionEngineInstallationError(
                f"Vellum verified the engine but could not install it at "
                f"{self._destination}: {error}"
            ) from error
        else:
            if backup_directory is not None:
                shutil.rmtree(backup_directory, ignore_errors=True)


def format_download_size(size_bytes: int) -> str:
    """Format an engine's exact declared size for the Settings window."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KiB"
    if size_bytes < 1024**3:
        return f"{size_bytes / 1024**2:.1f} MiB"
    return f"{size_bytes / 1024**3:.2f} GiB"


LARGE_V3_TURBO = TranscriptionEngineDescriptor(
    id=TranscriptionEngineId("large-v3-turbo"),
    display_name="large-v3-turbo",
    repository="deepdml/faster-whisper-large-v3-turbo-ct2",
    revision="4df90f75321148c3a29a9e2351b7ddf8f5b115a8",
    directory_name="large-v3-turbo",
    files=(
        EngineArtifact(
            "config.json",
            2_263,
            "b0253ea6c0d3bea6b1e19e91a02acfd3b53f4467362efcb5a3e6b16c9b3a9b7e",
        ),
        EngineArtifact(
            "model.bin",
            1_617_884_929,
            "e76620f83d5f5b69efd3d87e3dc180c1bd21df9fbebacfd4335e5e1efcc018da",
        ),
        EngineArtifact(
            "preprocessor_config.json",
            340,
            "7ccc62c6f2765af1f3b46c00c9b5894426835a05021c8b9c01eecb6dfb542711",
        ),
        EngineArtifact(
            "tokenizer.json",
            2_710_337,
            "297b13372ac43916285644fb9687add3cc62ee2a1adb60da3dc25cc94c1871fd",
        ),
        EngineArtifact(
            "vocabulary.json",
            1_068_114,
            "c69260f2ab26d659b7c398f9a2b2b48ed0df16c3b47d7326782fd9cba71690c1",
        ),
    ),
)

SUPPORTED_TRANSCRIPTION_ENGINES = (LARGE_V3_TURBO,)


def transcription_engine_by_id(
    engine_id: TranscriptionEngineId | str,
) -> TranscriptionEngineDescriptor:
    """Return the selectable engine identified by a persisted settings value."""
    if isinstance(engine_id, str):
        engine_id = TranscriptionEngineId(engine_id)
    if not isinstance(engine_id, TranscriptionEngineId):
        raise TypeError("A Transcription engine identifier must be text.")
    for descriptor in SUPPORTED_TRANSCRIPTION_ENGINES:
        if descriptor.id == engine_id:
            return descriptor
    raise ValueError(f"Vellum does not support the Transcription engine {str(engine_id)!r}.")
