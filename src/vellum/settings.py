"""Settings coordination and the native Vellum Settings window."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from vellum.config import InputDevice, Settings, SettingsStore, unambiguous_input_devices
from vellum.runtime import list_input_devices
from vellum.transcription_engines import (
    EngineDownloadProgress,
    TranscriptionEngineDescriptor,
    format_download_size,
)

EngineDownload = Callable[[Settings, Callable[[EngineDownloadProgress], None]], None]


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
        *,
        current_settings: Settings | None = None,
    ) -> None:
        self._store = store
        self._start_at_sign_in = start_at_sign_in
        self._on_settings_changed = on_settings_changed
        self._can_apply = can_apply or _allow_settings_change
        self._current_settings = current_settings if current_settings is not None else store.load()

    def sync_start_at_sign_in(self, settings: Settings) -> None:
        """Make an already-persisted preference effective at the next sign-in."""
        self._start_at_sign_in.set_enabled(settings.start_at_sign_in)

    def save(self, settings: Settings) -> None:
        """Apply Settings effects, persisting only a completed change."""
        self._can_apply(settings)
        runtime_applied = False
        start_at_sign_in_applied = False
        try:
            self._on_settings_changed(settings)
            runtime_applied = True
            self._start_at_sign_in.set_enabled(settings.start_at_sign_in)
            start_at_sign_in_applied = True
            self._store.save(settings)
        except Exception:
            if start_at_sign_in_applied:
                self._start_at_sign_in.set_enabled(self._current_settings.start_at_sign_in)
            if runtime_applied:
                self._on_settings_changed(self._current_settings)
            raise
        self._current_settings = settings


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
        engines: Sequence[TranscriptionEngineDescriptor] = (),
        engine_available: Callable[[TranscriptionEngineDescriptor], bool] | None = None,
        on_download: EngineDownload | None = None,
        on_check_for_updates: Callable[[], None] | None = None,
        on_copy_diagnostics: Callable[[], None] | None = None,
    ) -> None:
        self._settings = settings
        self._on_save = on_save
        self._input_devices = input_devices
        self._engines = tuple(engines)
        self._engine_available = engine_available or (lambda _: False)
        self._on_download = on_download
        self._on_check_for_updates = on_check_for_updates
        self._on_copy_diagnostics = on_copy_diagnostics

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
        device_choices = self._device_choices(devices)
        selected_device = self._selection_for_current_device(device_choices)
        input_device = tk.StringVar(value=selected_device)
        activation_hotkey = tk.StringVar(value=self._settings.activation_hotkey)
        sounds_enabled = tk.BooleanVar(value=self._settings.sounds_enabled)
        start_at_sign_in = tk.BooleanVar(value=self._settings.start_at_sign_in)
        vocabulary_hints = tk.Text(frame, width=48, height=4)
        vocabulary_hints.insert("1.0", "\n".join(self._settings.vocabulary_hints))
        error_text = tk.StringVar(value=load_error or "")

        engine_choices = {engine.display_name: engine for engine in self._engines}
        selected_engine = next(
            (
                label
                for label, engine in engine_choices.items()
                if engine.id == self._settings.transcription_engine_id
            ),
            next(iter(engine_choices), ""),
        )
        engine_selection = tk.StringVar(value=selected_engine)
        engine_information = tk.StringVar()
        download_status = tk.StringVar()

        def chosen_engine() -> TranscriptionEngineDescriptor | None:
            return engine_choices.get(engine_selection.get())

        def refresh_engine_information() -> None:
            engine = chosen_engine()
            if engine is None:
                return
            installed = (
                "Installed and verified locally"
                if self._engine_available(engine)
                else "Not downloaded"
            )
            download_size = format_download_size(engine.download_size_bytes)
            engine_information.set(
                f"Source: {engine.source_url}\nDownload: {download_size}\nStatus: {installed}"
            )

        def form_settings() -> Settings:
            device = device_choices.get(input_device.get())
            if input_device.get() not in device_choices:
                raise RuntimeError("Choose an Input device from the list.")
            engine = chosen_engine()
            if self._engines and engine is None:
                raise RuntimeError("Choose a Transcription engine from the list.")
            entered_hints = tuple(
                hint
                for line in vocabulary_hints.get("1.0", "end-1c").splitlines()
                for hint in line.split(",")
            )
            return Settings(
                input_device=device,
                activation_hotkey=activation_hotkey.get(),
                sounds_enabled=sounds_enabled.get(),
                start_at_sign_in=start_at_sign_in.get(),
                transcription_engine_id=(
                    self._settings.transcription_engine_id if engine is None else engine.id
                ),
                vocabulary_hints=entered_hints,
            )

        def save() -> None:
            try:
                self._on_save(form_settings())
            except Exception as error:
                error_text.set(str(error))
                return
            window.destroy()

        row = 0
        if self._engines:
            ttk.Label(frame, text="Transcription engine").grid(
                row=row, column=0, sticky="w", pady=(0, 4)
            )
            engine_selector = ttk.Combobox(
                frame,
                state="readonly",
                textvariable=engine_selection,
                values=tuple(engine_choices),
                width=48,
            )
            engine_selector.grid(row=row, column=1, sticky="ew", pady=(0, 4))
            engine_selector.bind("<<ComboboxSelected>>", lambda _: refresh_engine_information())
            row += 1
            ttk.Label(frame, textvariable=engine_information, wraplength=430).grid(
                row=row, column=1, sticky="w", pady=(0, 4)
            )
            refresh_engine_information()
            row += 1

            def update_download_progress(progress: EngineDownloadProgress) -> None:
                download_status.set(
                    f"{progress.current_file}: {progress.percentage}% "
                    f"({format_download_size(progress.downloaded_bytes)} of "
                    f"{format_download_size(progress.total_bytes)})"
                )
                window.update_idletasks()

            def download() -> None:
                if self._on_download is None:
                    error_text.set(
                        "Transcription engine downloads are not available in this Vellum session."
                    )
                    return
                try:
                    updated_settings = form_settings()
                    self._on_save(updated_settings)
                    self._on_download(updated_settings, update_download_progress)
                except Exception as error:
                    error_text.set(str(error))
                    return
                download_status.set(
                    "Verified download; Vellum is warming the local Transcription engine."
                )
                refresh_engine_information()

            ttk.Button(
                frame, text="Download and verify Transcription engine", command=download
            ).grid(row=row, column=1, sticky="w", pady=(0, 2))
            row += 1
            ttk.Label(frame, textvariable=download_status, wraplength=430).grid(
                row=row, column=1, sticky="w", pady=(0, 4)
            )
            row += 1

        ttk.Label(frame, text="Input device").grid(row=row, column=0, sticky="w", pady=(0, 4))
        device_selector = ttk.Combobox(
            frame,
            state="readonly",
            textvariable=input_device,
            values=tuple(device_choices),
            width=48,
        )
        device_selector.grid(row=row, column=1, sticky="ew", pady=(0, 4))
        row += 1

        ttk.Label(frame, text="Activation hotkey").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=activation_hotkey, width=24).grid(
            row=row, column=1, sticky="w", pady=4
        )
        row += 1
        ttk.Label(frame, text="Example: Ctrl+Alt+Space").grid(
            row=row, column=1, sticky="w", pady=(0, 4)
        )
        row += 1
        ttk.Checkbutton(frame, text="Play capture sounds", variable=sounds_enabled).grid(
            row=row, column=1, sticky="w", pady=4
        )
        row += 1
        ttk.Checkbutton(frame, text="Start Vellum when I sign in", variable=start_at_sign_in).grid(
            row=row, column=1, sticky="w", pady=4
        )
        row += 1
        ttk.Label(frame, text="Vocabulary hints").grid(row=row, column=0, sticky="nw", pady=4)
        vocabulary_hints.grid(row=row, column=1, sticky="ew", pady=4)
        row += 1
        ttk.Label(
            frame,
            text="One term per line or comma-separated. Vellum is always included.",
            wraplength=430,
        ).grid(row=row, column=1, sticky="w", pady=(0, 4))
        row += 1
        ttk.Label(frame, textvariable=error_text, foreground="#b91c1c", wraplength=430).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(4, 8)
        )
        row += 1

        release_tools = ttk.Frame(frame)
        release_tools.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 8))
        if self._on_check_for_updates is not None:
            ttk.Button(
                release_tools,
                text="Check for updates",
                command=self._on_check_for_updates,
            ).grid(row=0, column=0, padx=(0, 6))
        if self._on_copy_diagnostics is not None:
            ttk.Button(
                release_tools,
                text="Copy redacted diagnostics",
                command=self._on_copy_diagnostics,
            ).grid(row=0, column=1)
        row += 1

        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, columnspan=2, sticky="e")
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
        for device in unambiguous_input_devices(devices):
            choices[device.display_name] = device
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
