"""Windows adapters for focus, clipboard, and Text insertion."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


class WindowsFocus:
    """Identifies an Insertion target by its foreground window handle."""

    def foreground_target(self) -> int:
        self._require_windows()
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        target = user32.GetForegroundWindow()
        if not target:
            raise RuntimeError("Vellum could not identify the foreground Insertion target.")
        return int(target)

    @staticmethod
    def _require_windows() -> None:
        if sys.platform != "win32":
            raise RuntimeError("Vellum supports Windows only.")


class WindowsClipboard:
    def copy(self, text: str) -> None:
        try:
            import pyperclip
        except ImportError as error:
            raise RuntimeError("The pyperclip clipboard runtime is not installed.") from error
        pyperclip.copy(text)


class WindowsPaste:
    """Sends Ctrl+V without synthesising the Transcript as individual keystrokes."""

    _VK_CONTROL = 0x11
    _VK_V = 0x56
    _KEYEVENTF_KEYUP = 0x0002

    def paste(self) -> None:
        WindowsFocus._require_windows()
        if self._foreground_target_is_elevated() and not self._current_process_is_elevated():
            raise PermissionError(
                "The Insertion target is elevated and cannot receive Vellum's Ctrl+V; "
                "the Transcript remains in the clipboard."
            )
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.keybd_event(self._VK_CONTROL, 0, 0, 0)
        user32.keybd_event(self._VK_V, 0, 0, 0)
        user32.keybd_event(self._VK_V, 0, self._KEYEVENTF_KEYUP, 0)
        user32.keybd_event(self._VK_CONTROL, 0, self._KEYEVENTF_KEYUP, 0)

    @classmethod
    def _foreground_target_is_elevated(cls) -> bool:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        kernel32.OpenProcess.restype = wintypes.HANDLE
        process_id = wintypes.DWORD()
        target = user32.GetForegroundWindow()
        user32.GetWindowThreadProcessId(target, ctypes.byref(process_id))
        process = kernel32.OpenProcess(0x1000, False, process_id.value)
        if not process:
            return False
        try:
            return cls._token_is_elevated(process)
        finally:
            kernel32.CloseHandle(process)

    @classmethod
    def _current_process_is_elevated(cls) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        return cls._token_is_elevated(kernel32.GetCurrentProcess())

    @staticmethod
    def _token_is_elevated(process: int) -> bool:
        class TokenElevation(ctypes.Structure):
            _fields_ = [("TokenIsElevated", wintypes.DWORD)]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(process, 0x0008, ctypes.byref(token)):
            return False
        try:
            elevation = TokenElevation()
            if not advapi32.GetTokenInformation(
                token,
                20,
                ctypes.byref(elevation),
                ctypes.sizeof(elevation),
                None,
            ):
                return False
            return bool(elevation.TokenIsElevated)
        finally:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(token)
