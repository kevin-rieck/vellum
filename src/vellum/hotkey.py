"""System-wide Ctrl+Alt+Space Push-to-talk adapter."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock, Thread, Timer
from typing import Any

from vellum.session import MAXIMUM_DICTATION_SECONDS, DictationSession, PendingTranscription


class PushToTalkHotkey:
    """Starts on Activation hotkey press and ends on release or the duration limit."""

    def __init__(self, session: DictationSession, on_error: Callable[[Exception], None]) -> None:
        self._session = session
        self._on_error = on_error
        self._listener: Any | None = None
        self._ctrl_down = False
        self._alt_down = False
        self._activation_held = False
        self._capture_active = False
        self._capture_lock = Lock()
        self._limit_timer: Timer | None = None
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
            if releases_activation:
                with self._capture_lock:
                    self._activation_held = False
                self._end_capture_if_active()
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
        with self._capture_lock:
            timer = self._limit_timer
            self._limit_timer = None
            self._capture_active = False
        if timer is not None:
            timer.cancel()

    def _start_session(self) -> None:
        if not self._enabled:
            return
        try:
            with self._capture_lock:
                if self._activation_held:
                    return
                self._activation_held = True
                if self._session.active:
                    return
                self._session.start()
                self._capture_active = True
                timer = Timer(MAXIMUM_DICTATION_SECONDS, self._end_capture_if_active)
                self._limit_timer = timer
        except Exception as error:
            self._on_error(error)
            return
        timer.start()

    def _end_capture_if_active(self) -> None:
        """End capture once, whether hotkey release or the duration limit wins."""
        with self._capture_lock:
            if not self._capture_active:
                return
            self._capture_active = False
            timer = self._limit_timer
            self._limit_timer = None
        if timer is not None:
            timer.cancel()
        self._end_capture()

    def _end_capture(self) -> None:
        try:
            pending = self._session.end_capture()
        except Exception as error:
            self._on_error(error)
            return
        Thread(target=self._finish_session, args=(pending,), daemon=True).start()

    def _finish_session(self, pending: PendingTranscription) -> None:
        try:
            self._session.finish_transcription(pending)
        except Exception as error:
            self._on_error(error)
