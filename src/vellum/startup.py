"""Startup prerequisite validation for Vellum's local-only runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StartupPrerequisiteError(RuntimeError):
    """Raised before capture begins when required local runtime support is absent."""


class PrerequisiteProbe(Protocol):
    @property
    def cuda_available(self) -> bool: ...

    @property
    def engine_available(self) -> bool: ...

    @property
    def engine_directory(self) -> Path: ...


def require_startup_prerequisites(probe: PrerequisiteProbe) -> None:
    """Fail with every missing prerequisite, rather than failing later in a session."""
    missing: list[str] = []
    if not probe.cuda_available:
        missing.append("a CUDA-capable NVIDIA GPU usable by CTranslate2")
    if not probe.engine_available:
        missing.append(
            f"the local large-v3-turbo Transcription engine "
            f"(expected at {probe.engine_directory})"
        )

    if missing:
        bullets = "\n".join(f"- {item}" for item in missing)
        raise StartupPrerequisiteError(f"Vellum cannot start; install or configure:\n{bullets}")
