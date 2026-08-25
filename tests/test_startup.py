from __future__ import annotations

from pathlib import Path
from re import escape

import pytest

from vellum.startup import StartupPrerequisiteError, require_startup_prerequisites


class FakeProbe:
    def __init__(self, *, cuda_available: bool, engine_available: bool) -> None:
        self.cuda_available = cuda_available
        self.engine_available = engine_available
        self.engine_directory = Path("C:/Vellum/models/large-v3-turbo")


def test_startup_fails_clearly_when_cuda_is_unavailable() -> None:
    with pytest.raises(StartupPrerequisiteError, match="CUDA-capable NVIDIA GPU"):
        require_startup_prerequisites(FakeProbe(cuda_available=False, engine_available=True))


def test_startup_fails_clearly_when_the_required_engine_is_unavailable() -> None:
    probe = FakeProbe(cuda_available=True, engine_available=False)

    with pytest.raises(
        StartupPrerequisiteError,
        match=f"large-v3-turbo.*{escape(str(probe.engine_directory))}",
    ):
        require_startup_prerequisites(probe)


def test_startup_allows_a_cuda_machine_with_the_required_local_engine() -> None:
    require_startup_prerequisites(FakeProbe(cuda_available=True, engine_available=True))
