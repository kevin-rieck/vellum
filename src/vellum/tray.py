"""System-tray feedback and Settings entry point for the Vellum application."""

from __future__ import annotations

from threading import Lock
from typing import Any

from vellum.config import Settings
from vellum.diagnostics import log_error
from vellum.hotkey import PushToTalkHotkey
from vellum.session import SessionFeedback
from vellum.settings import SettingsController, SettingsWindow
from vellum.sounds import WindowsSessionSounds


class TrayApplication:
    """Owns visible Session feedback, Settings, and the Quit command."""

    def __init__(self, settings: Settings | None = None) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError as error:
            raise RuntimeError("The pystray system-tray runtime is not installed.") from error

        self._pystray = pystray
        self._hotkey: PushToTalkHotkey | None = None
        self._settings = settings or Settings()
        self._settings_controller: SettingsController | None = None
        self._sounds = WindowsSessionSounds(enabled=self._settings.sounds_enabled)
        self._startup_failed = False
        self._icon_registered = False
        self._notification_lock = Lock()
        self._pending_notifications: list[tuple[str, str]] = []
        self._images = {
            SessionFeedback.IDLE: self._image(Image, ImageDraw, "#3b82f6"),
            SessionFeedback.RECORDING: self._image(Image, ImageDraw, "#dc2626"),
            SessionFeedback.TRANSCRIBING: self._image(Image, ImageDraw, "#f59e0b"),
            SessionFeedback.CANCELLED: self._image(Image, ImageDraw, "#f59e0b"),
            SessionFeedback.NO_SPEECH: self._image(Image, ImageDraw, "#f59e0b"),
            SessionFeedback.ERROR: self._image(Image, ImageDraw, "#dc2626"),
        }
        self._icon: Any = pystray.Icon(
            "vellum",
            self._images[SessionFeedback.IDLE],
            self._ready_title(),
            pystray.Menu(
                pystray.MenuItem("Settings", self._open_settings),
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def set_settings_controller(self, settings_controller: SettingsController) -> None:
        self._settings_controller = settings_controller

    def apply_settings(self, settings: Settings) -> None:
        """Reflect a saved preference set in the tray without retaining session data."""
        self._settings = settings
        self._sounds.set_enabled(settings.sounds_enabled)
        if self._icon.icon == self._images[SessionFeedback.IDLE]:
            self._icon.title = self._ready_title()

    def run(self, hotkey: PushToTalkHotkey | None = None) -> bool:
        """Register the tray icon before delivering any queued notifications."""
        self._hotkey = hotkey
        if hotkey is not None and not self._startup_failed:
            try:
                hotkey.start()
            except Exception as error:
                self.fail_startup(error)
        self._icon.run(self._on_icon_ready)
        return not self._startup_failed

    def warming(self) -> None:
        self._icon.title = "Vellum — warming local Transcription engine"

    def fail_startup(self, error: Exception) -> None:
        """Keep an error-state Tray application available until the user quits."""
        self._startup_failed = True
        if self._hotkey is not None:
            self._hotkey.stop()
        self.report_error(error)

    def feedback(self, feedback: SessionFeedback) -> None:
        if feedback is SessionFeedback.RECORDING:
            self._sounds.play_start()
        elif feedback is SessionFeedback.TRANSCRIBING:
            self._sounds.play_end()
        self._icon.icon = self._images[feedback]
        self._icon.title = (
            self._ready_title()
            if feedback is SessionFeedback.IDLE
            else f"Vellum — {feedback.value}"
        )
        if feedback is SessionFeedback.CANCELLED:
            self._notify(
                "The insertion target changed. The Transcript is available in the clipboard.",
                "Vellum insertion cancelled",
            )
        elif feedback is SessionFeedback.NO_SPEECH:
            self._notify(
                "No usable speech was detected; the clipboard was not changed.", "Vellum"
            )

    def report_error(self, error: Exception) -> None:
        """Show and persist failures raised during a Dictation session."""
        log_error(error)
        self.feedback(SessionFeedback.ERROR)
        self._notify(str(error), "Vellum error")

    def _on_icon_ready(self, icon: Any) -> None:
        """Make the icon visible, then deliver notifications queued during startup."""
        icon.visible = True
        with self._notification_lock:
            self._icon_registered = True
            pending_notifications = self._pending_notifications
            self._pending_notifications = []
        for message, title in pending_notifications:
            icon.notify(message, title)

    def _notify(self, message: str, title: str) -> None:
        with self._notification_lock:
            if not self._icon_registered:
                self._pending_notifications.append((message, title))
                return
        self._icon.notify(message, title)

    def _open_settings(self, icon: Any, item: Any) -> None:
        del icon, item
        if self._settings_controller is None:
            self.report_error(RuntimeError("Vellum Settings are not available yet."))
            return
        try:
            SettingsWindow(self._settings, self._settings_controller.save).show()
        except Exception as error:
            self.report_error(error)

    def _quit(self, icon: Any, item: Any) -> None:
        del item
        if self._hotkey is not None:
            self._hotkey.stop()
        icon.stop()

    def _ready_title(self) -> str:
        return f"Vellum — ready ({self._settings.activation_hotkey})"

    @staticmethod
    def _image(image: Any, image_draw: Any, colour: str) -> Any:
        canvas = image.new("RGBA", (64, 64), (0, 0, 0, 0))
        drawing = image_draw.Draw(canvas)
        drawing.ellipse((8, 8, 56, 56), fill=colour)
        return canvas
