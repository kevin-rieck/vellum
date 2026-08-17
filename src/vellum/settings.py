"""Settings coordination and the native Vellum Settings window."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from vellum.config import InputDevice, Settings, SettingsStore
from vellum.runtime import list_input_devices


class StartAtSignIn(Protocol):
    def set_enabled(self, enabled: bool) -> None: ...


class SettingsController:
    """Persists Settings and applies their Windows-specific effects."""

    def __init__(
        self,
        store: SettingsStore,
        start_at_sign_in: StartAtSignIn,
        on_settings_changed: Callable[[Settings], None],
        can_apply: Callable[[Settings], None] | None = None,
    ) -> None:
        self._store = store
        self._start_at_sign_in = start_at_sign_in
        self._on_settings_changed = on_settings_changed
        self._can_apply = can_apply or _allow_settings_change

    def sync_start_at_sign_in(self, settings: Settings) -> None:
        """Make an already-persisted preference effective at the next sign-in."""
        self._start_at_sign_in.set_enabled(settings.start_at_sign_in)

    def save(self, settings: Settings) -> None:
        """Persist Settings before applying their external and runtime effects."""
        self._can_apply(settings)
        self._store.save(settings)
        self._start_at_sign_in.set_enabled(settings.start_at_sign_in)
        self._on_settings_changed(settings)


def _allow_settings_change(settings: Settings) -> None:
    del settings


class SettingsWindow:
    """A small native Tk window opened from the Vellum tray menu."""

    _WINDOWS_DEFAULT = "Windows default Input device"

    def __init__(
        self,
        settings: Settings,
        on_save: Callable[[Settings], None],
        *,
        input_devices: Callable[[], Sequence[InputDevice]] = list_input_devices,
    ) -> None:
        self._settings = settings
        self._on_save = on_save
        self._input_devices = input_devices

    def show(self) -> None:
        """Open the Settings form and keep all choices in local process memory."""
        try:
            import tkinter as tk
            from tkinter import ttk
        except ImportError as error:
            raise RuntimeError("The native Windows Settings window is unavailable.") from error

        window = tk.Tk()
        window.title("Vellum Settings")
        window.resizable(False, False)
        frame = ttk.Frame(window, padding=12)
        frame.grid(sticky="nsew")

        devices, load_error = self._available_devices()
        choices = self._device_choices(devices)
        selected_device = self._selection_for_current_device(choices)
        input_device = tk.StringVar(value=selected_device)
        activation_hotkey = tk.StringVar(value=self._settings.activation_hotkey)
        sounds_enabled = tk.BooleanVar(value=self._settings.sounds_enabled)
        start_at_sign_in = tk.BooleanVar(value=self._settings.start_at_sign_in)
        error_text = tk.StringVar(value=load_error or "")

        ttk.Label(frame, text="Input device").grid(row=0, column=0, sticky="w", pady=(0, 4))
        device_selector = ttk.Combobox(
            frame,
            state="readonly",
            textvariable=input_device,
            values=tuple(choices),
            width=48,
        )
        device_selector.grid(row=0, column=1, sticky="ew", pady=(0, 4))

        ttk.Label(frame, text="Activation hotkey").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=activation_hotkey, width=24).grid(
            row=1, column=1, sticky="w", pady=4
        )
        ttk.Label(frame, text="Example: Ctrl+Alt+Space").grid(
            row=2, column=1, sticky="w", pady=(0, 4)
        )
        ttk.Checkbutton(frame, text="Play capture sounds", variable=sounds_enabled).grid(
            row=3, column=1, sticky="w", pady=4
        )
        ttk.Checkbutton(frame, text="Start Vellum when I sign in", variable=start_at_sign_in).grid(
            row=4, column=1, sticky="w", pady=4
        )
        ttk.Label(frame, textvariable=error_text, foreground="#b91c1c", wraplength=430).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(4, 8)
        )

        def save() -> None:
            try:
                device = choices.get(input_device.get())
                if input_device.get() not in choices:
                    raise RuntimeError("Choose an Input device from the list.")
                self._on_save(
                    Settings(
                        input_device=device,
                        activation_hotkey=activation_hotkey.get(),
                        sounds_enabled=sounds_enabled.get(),
                        start_at_sign_in=start_at_sign_in.get(),
                    )
                )
            except Exception as error:
                error_text.set(str(error))
                return
            window.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=window.destroy).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(buttons, text="Save", command=save).grid(row=0, column=1)
        window.mainloop()

    def _available_devices(self) -> tuple[tuple[InputDevice, ...], str | None]:
        try:
            return tuple(self._input_devices()), None
        except RuntimeError as error:
            return (), str(error)

    def _device_choices(self, devices: Sequence[InputDevice]) -> dict[str, InputDevice | None]:
        choices: dict[str, InputDevice | None] = {self._WINDOWS_DEFAULT: None}
        for index, device in enumerate(devices, start=1):
            label = device.display_name
            if label in choices:
                label = f"{label} [{index}]"
            choices[label] = device
        return choices

    def _selection_for_current_device(self, choices: dict[str, InputDevice | None]) -> str:
        for label, device in choices.items():
            if device == self._settings.input_device:
                return label
        if self._settings.input_device is None:
            return self._WINDOWS_DEFAULT

        unavailable_label = f"{self._settings.input_device.display_name} — unavailable"
        choices[unavailable_label] = self._settings.input_device
        return unavailable_label
