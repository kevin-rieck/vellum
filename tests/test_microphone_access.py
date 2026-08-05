from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from vellum.runtime import SoundDeviceRecorder


class AccessDeniedError(Exception):
    pass


def test_recorder_explains_how_to_grant_windows_microphone_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_access(**_: object) -> object:
        raise AccessDeniedError("MME error 1")

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(InputStream=deny_access, PortAudioError=AccessDeniedError),
    )

    with pytest.raises(RuntimeError, match="Let desktop apps access your microphone"):
        SoundDeviceRecorder().start()
