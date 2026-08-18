"""Windows adapters for focus, clipboard, and Text insertion."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes

from vellum.session import InsertionTarget


def build_start_at_sign_in_command(executable: str | None = None) -> str:
    """Build a correctly quoted user-level command to launch Vellum at sign-in."""
    return subprocess.list2cmdline([executable or sys.executable, "-m", "vellum.app"])


class WindowsStartAtSignIn:
    """Owns Vellum's HKCU Run registration; it never requests elevation."""

    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _VALUE_NAME = "Vellum"

    def __init__(self, command: str | None = None) -> None:
        self._command = command or build_start_at_sign_in_command()

    def set_enabled(self, enabled: bool) -> None:
        WindowsFocus._require_windows()
        try:
            import winreg
        except ImportError as error:
            raise RuntimeError("The Windows start-at-sign-in runtime is unavailable.") from error

        try:
            if enabled:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY) as key:
                    winreg.SetValueEx(key, self._VALUE_NAME, 0, winreg.REG_SZ, self._command)
            else:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER, self._RUN_KEY, 0, winreg.KEY_SET_VALUE
                    ) as key:
                        winreg.DeleteValue(key, self._VALUE_NAME)
                except FileNotFoundError:
                    # There is nothing to remove when Vellum has never been enabled.
                    return
        except OSError as error:
            raise RuntimeError(
                "Vellum could not update its start-at-sign-in preference."
            ) from error


class WindowsFocus:
    """Identifies an Insertion target by its foreground window handle."""

    def foreground_target(self) -> InsertionTarget:
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

    def paste(self, insertion_target: InsertionTarget) -> bool:
        """Paste only when the capture-end target is still foreground and safe."""
        WindowsFocus._require_windows()
        if WindowsFocus().foreground_target() != insertion_target:
            return False
        if self._target_is_elevated(insertion_target) and not self._current_process_is_elevated():
            raise PermissionError(
                "The Insertion target is elevated and cannot receive Vellum's Ctrl+V; "
                "the Transcript remains in the clipboard."
            )
        if WindowsFocus().foreground_target() != insertion_target:
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.keybd_event(self._VK_CONTROL, 0, 0, 0)
        user32.keybd_event(self._VK_V, 0, 0, 0)
        user32.keybd_event(self._VK_V, 0, self._KEYEVENTF_KEYUP, 0)
        user32.keybd_event(self._VK_CONTROL, 0, self._KEYEVENTF_KEYUP, 0)
        return True

    @classmethod
    def _target_is_elevated(cls, target: InsertionTarget) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        process_id = wintypes.DWORD()
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if not user32.GetWindowThreadProcessId(target, ctypes.byref(process_id)):
            raise PermissionError(
                "Vellum could not verify the Insertion target's permissions; "
                "the Transcript remains in the clipboard."
            )
        process = kernel32.OpenProcess(0x1000, False, process_id.value)
        if not process:
            raise PermissionError(
                "Vellum could not verify the Insertion target's permissions; "
                "the Transcript remains in the clipboard."
            )
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
    def _token_is_elevated(process: wintypes.HANDLE) -> bool:
        class TokenElevation(ctypes.Structure):
            _fields_ = [("TokenIsElevated", wintypes.DWORD)]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        open_process_token = advapi32.OpenProcessToken
        open_process_token.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        open_process_token.restype = wintypes.BOOL
        get_token_information = advapi32.GetTokenInformation
        get_token_information.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        get_token_information.restype = wintypes.BOOL

        token = wintypes.HANDLE()
        if not open_process_token(process, 0x0008, ctypes.byref(token)):
            raise PermissionError("Vellum could not verify process elevation.")
        try:
            elevation = TokenElevation()
            returned_length = wintypes.DWORD()
            if not get_token_information(
                token,
                20,
                ctypes.byref(elevation),
                ctypes.sizeof(elevation),
                ctypes.byref(returned_length),
            ):
                raise PermissionError("Vellum could not verify process elevation.")
            return bool(elevation.TokenIsElevated)
        finally:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(token)
