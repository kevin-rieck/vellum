"""Small runtime configuration surface for the first Vellum tracer bullet."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VellumPaths:
    """Locations owned by Vellum; no Dictation session data is persisted here."""

    model_directory: Path
    application_directory: Path

    @property
    def diagnostics_log_file(self) -> Path:
        """The local error log; it never contains audio or Transcripts."""
        return self.application_directory / "vellum.log"

    @classmethod
    def from_environment(cls) -> VellumPaths:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        application_directory = local_app_data / "Vellum"
        configured_model = os.environ.get("VELLUM_MODEL_DIR")
        if configured_model:
            return cls(
                model_directory=Path(configured_model).expanduser(),
                application_directory=application_directory,
            )

        return cls(
            model_directory=application_directory / "models" / "large-v3-turbo",
            application_directory=application_directory,
        )
