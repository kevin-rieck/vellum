"""Small runtime configuration surface for the first Vellum tracer bullet."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VellumPaths:
    """Locations owned by Vellum; no Dictation session data is persisted here."""

    model_directory: Path

    @classmethod
    def from_environment(cls) -> VellumPaths:
        configured_model = os.environ.get("VELLUM_MODEL_DIR")
        if configured_model:
            return cls(model_directory=Path(configured_model).expanduser())

        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return cls(model_directory=local_app_data / "Vellum" / "models" / "large-v3-turbo")
