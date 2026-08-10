"""System-wide Ctrl+Alt+Space Push-to-talk adapter."""

from __future__ import annotations

from collections.abc import Callable
from threading import Thread
from typing import Any

from vellum.session import DictationSession


class PushToTalkHotkey:
    """Starts at the default Activation hotkey press and finishes on its release."""

    def __init__(self, session: DictationSession, on_error: Callable[[Exception], None]) -> None:
        self._session = session
        self._on_error = on_error
        self._listener: Any | None = None
        self._ctrl_down = False
        self._alt_down = False
        self._awaiting_release = False
        self._enabled = False

    def enable(self) -> None:
        """Allow activation only after the Transcription engine has warmed successfully."""
        self._enabled = True

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError as error:
            raise RuntimeError("The pynput global-hotkey runtime is not installed.") from error

        ctrl_keys = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
        alt_keys = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r}

        def on_press(key: object) -> None:
            self._ctrl_down = self._ctrl_down or key in ctrl_keys
            self._alt_down = self._alt_down or key in alt_keys
            if key == keyboard.Key.space and self._ctrl_down and self._alt_down:
                self._start_session()

        def on_release(key: object) -> None:
            releases_activation = key == keyboard.Key.space or key in ctrl_keys or key in alt_keys
            if releases_activation and self._awaiting_release:
                self._awaiting_release = False
                self._finish_from_release()
            if key in ctrl_keys:
                self._ctrl_down = False
            if key in alt_keys:
                self._alt_down = False

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _start_session(self) -> None:
        if not self._enabled or self._session.active:
            return
        try:
            self._session.start()
            self._awaiting_release = True
        except Exception as error:
            self._on_error(error)

    def _finish_from_release(self) -> None:
        try:
            insertion_target = self._session.capture_insertion_target()
        except Exception as error:
            self._session.fail_release()
            self._on_error(error)
            return
        try:
            audio, insertion_target = self._session.begin_transcription(insertion_target)
        except Exception as error:
            self._on_error(error)
            return
        Thread(
            target=self._finish_session, args=(audio, insertion_target), daemon=True
        ).start()

    def _finish_session(self, audio: object, insertion_target: object) -> None:
        try:
            self._session.finish_transcription(audio, insertion_target)
        except Exception as error:
            self._on_error(error)
