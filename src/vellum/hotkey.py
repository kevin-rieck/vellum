"""Configurable system-wide Push-to-talk adapter."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock, Thread, Timer
from typing import Any

from vellum.config import normalise_activation_hotkey
from vellum.session import MAXIMUM_DICTATION_SECONDS, DictationSession, PendingTranscription


class PushToTalkHotkey:
    """Starts on Activation hotkey press and ends on release or the duration limit."""

    def __init__(
        self,
        session: DictationSession,
        on_error: Callable[[Exception], None],
        activation_hotkey: str = "Ctrl+Alt+Space",
    ) -> None:
        self._session = session
        self._on_error = on_error
        self._activation_hotkey = normalise_activation_hotkey(activation_hotkey)
        self._listener: Any | None = None
        self._modifier_keys: dict[str, set[object]] = {}
        self._activation_key_held = False
        self._activation_held = False
        self._capture_active = False
        self._capture_lock = Lock()
        self._limit_timer: Timer | None = None
        self._enabled = False

    @property
    def activation_hotkey(self) -> str:
        return self._activation_hotkey

    def enable(self) -> None:
        """Allow activation only after the Transcription engine has warmed successfully."""
        self._enabled = True

    def configure(self, activation_hotkey: str) -> None:
        """Replace the listener after a Settings change when no session is active."""
        configured_hotkey = normalise_activation_hotkey(activation_hotkey)
        if configured_hotkey == self._activation_hotkey:
            return
        if self._session.active:
            raise RuntimeError("Release Push-to-talk before changing the Activation hotkey.")

        listener = self._listener
        self._activation_hotkey = configured_hotkey
        self._reset_pressed_keys()
        if listener is not None:
            listener.stop()
            self._listener = None
            self.start()

    def start(self) -> None:
        if self._listener is not None:
            return
        try:
            from pynput import keyboard
        except ImportError as error:
            raise RuntimeError("The pynput global-hotkey runtime is not installed.") from error

        modifiers, activation_key = _keyboard_keys(keyboard, self._activation_hotkey)
        self._modifier_keys = {modifier: set() for modifier in modifiers}

        def on_press(key: object) -> None:
            for modifier, keys in modifiers.items():
                if key in keys:
                    self._modifier_keys[modifier].add(key)
            if _matches_activation_key(keyboard, key, activation_key):
                self._activation_key_held = True
            self._start_if_activation_is_held()

        def on_release(key: object) -> None:
            for modifier, keys in modifiers.items():
                if key in keys:
                    self._modifier_keys[modifier].discard(key)
            if _matches_activation_key(keyboard, key, activation_key):
                self._activation_key_held = False
            if not self._activation_is_pressed():
                with self._capture_lock:
                    self._activation_held = False
                self._end_capture_if_active()

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._reset_pressed_keys()
        with self._capture_lock:
            timer = self._limit_timer
            self._limit_timer = None
            self._capture_active = False
        if timer is not None:
            timer.cancel()

    def _reset_pressed_keys(self) -> None:
        self._modifier_keys = {}
        self._activation_key_held = False
        self._activation_held = False

    def _activation_is_pressed(self) -> bool:
        return self._activation_key_held and all(self._modifier_keys.values())

    def _start_if_activation_is_held(self) -> None:
        if self._activation_is_pressed():
            self._start_session()

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


def _keyboard_keys(keyboard: Any, activation_hotkey: str) -> tuple[dict[str, set[object]], str]:
    parts = activation_hotkey.split("+")
    modifier_names, activation_key = parts[:-1], parts[-1]
    named_keys = keyboard.Key
    aliases = {
        "Ctrl": ("ctrl", "ctrl_l", "ctrl_r"),
        "Alt": ("alt", "alt_l", "alt_r"),
        "Shift": ("shift", "shift_l", "shift_r"),
        "Win": ("cmd", "cmd_l", "cmd_r"),
    }
    modifiers: dict[str, set[object]] = {}
    for modifier_name in modifier_names:
        modifiers[modifier_name] = {
            getattr(named_keys, key_name)
            for key_name in aliases[modifier_name]
            if hasattr(named_keys, key_name)
        }
    return modifiers, activation_key


def _matches_activation_key(keyboard: Any, key: object, activation_key: str) -> bool:
    if len(activation_key) == 1:
        character = getattr(key, "char", None)
        if isinstance(character, str) and character.casefold() == activation_key.casefold():
            return True
        # Pynput translates a shifted digit (for example Shift+1) to "!". Its
        # virtual-key code still identifies the configured physical key.
        return getattr(key, "vk", None) == ord(activation_key.upper())
    named_key = {
        "Space": "space",
        "Enter": "enter",
        "Tab": "tab",
        "Esc": "esc",
    }.get(activation_key, activation_key.lower())
    return bool(key == getattr(keyboard.Key, named_key))
