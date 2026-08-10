"""Brief local audio cues for Dictation session capture boundaries."""

from __future__ import annotations

import sys


class WindowsSessionSounds:
    """Plays capture-start and capture-end sounds without persisting session data."""

    def play_start(self) -> None:
        self._play(0x00000000)  # MB_OK

    def play_end(self) -> None:
        self._play(0x00000040)  # MB_ICONASTERISK

    @staticmethod
    def _play(sound: int) -> None:
        if sys.platform != "win32":
            return
        try:
            import winsound

            winsound.MessageBeep(sound)
        except RuntimeError:
            # Session feedback must not prevent local capture or transcription.
            return
