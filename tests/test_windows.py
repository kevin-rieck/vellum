from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from vellum.windows import (
    WindowsFocus,
    WindowsPaste,
    WindowsStartAtSignIn,
    build_start_at_sign_in_command,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows adapter requires Windows APIs")
def test_current_process_elevation_query_returns_a_boolean() -> None:
    assert isinstance(WindowsPaste._current_process_is_elevated(), bool)


def test_paste_skips_a_target_that_is_no_longer_foreground(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vellum.windows.sys.platform", "win32")
    monkeypatch.setattr(WindowsFocus, "foreground_target", lambda _: 202)

    assert WindowsPaste().paste(101) is False


def test_paste_refuses_an_elevated_target_without_injecting_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vellum.windows.sys.platform", "win32")
    monkeypatch.setattr(WindowsFocus, "foreground_target", lambda _: 101)
    monkeypatch.setattr(WindowsPaste, "_target_is_elevated", lambda _, __: True)
    monkeypatch.setattr(WindowsPaste, "_current_process_is_elevated", lambda _: False)

    with pytest.raises(PermissionError, match="elevated"):
        WindowsPaste().paste(101)


def test_paste_refuses_an_uninspectable_target_without_injecting_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vellum.windows.sys.platform", "win32")
    monkeypatch.setattr(WindowsFocus, "foreground_target", lambda _: 101)

    def cannot_inspect(_: object, __: object) -> bool:
        raise PermissionError("Vellum could not verify the Insertion target's permissions.")

    monkeypatch.setattr(WindowsPaste, "_target_is_elevated", cannot_inspect)

    with pytest.raises(PermissionError, match="could not verify"):
        WindowsPaste().paste(101)


def test_paste_skips_a_target_that_loses_focus_during_permission_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int, int]] = []
    foreground = {"target": 101}

    class User32:
        def keybd_event(self, key: int, scan: int, flags: int, extra: int) -> None:
            calls.append((key, scan, flags, extra))

    def target_is_elevated(_: object, __: object) -> bool:
        foreground["target"] = 202
        return False

    monkeypatch.setattr("vellum.windows.sys.platform", "win32")
    monkeypatch.setattr(WindowsFocus, "foreground_target", lambda _: foreground["target"])
    monkeypatch.setattr(WindowsPaste, "_target_is_elevated", target_is_elevated)
    monkeypatch.setattr("vellum.windows.ctypes.WinDLL", lambda *_args, **_kwargs: User32())

    assert WindowsPaste().paste(101) is False
    assert calls == []


def test_paste_injects_keys_for_a_verified_same_privilege_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int, int]] = []

    class User32:
        def keybd_event(self, key: int, scan: int, flags: int, extra: int) -> None:
            calls.append((key, scan, flags, extra))

    monkeypatch.setattr("vellum.windows.sys.platform", "win32")
    monkeypatch.setattr(WindowsFocus, "foreground_target", lambda _: 101)
    monkeypatch.setattr(WindowsPaste, "_target_is_elevated", lambda _, __: False)
    monkeypatch.setattr("vellum.windows.ctypes.WinDLL", lambda *_args, **_kwargs: User32())

    assert WindowsPaste().paste(101) is True
    assert calls == [
        (WindowsPaste._VK_CONTROL, 0, 0, 0),
        (WindowsPaste._VK_V, 0, 0, 0),
        (WindowsPaste._VK_V, 0, WindowsPaste._KEYEVENTF_KEYUP, 0),
        (WindowsPaste._VK_CONTROL, 0, WindowsPaste._KEYEVENTF_KEYUP, 0),
    ]


def test_start_at_sign_in_uses_the_current_user_run_key_and_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values: dict[str, str] = {}

    class RegistryKey:
        def __enter__(self) -> RegistryKey:
            return self

        def __exit__(self, *_: object) -> None:
            pass

    def create_key(root: object, path: str) -> RegistryKey:
        assert root is registry.HKEY_CURRENT_USER
        assert path == WindowsStartAtSignIn._RUN_KEY
        return RegistryKey()

    def open_key(root: object, path: str, reserved: int, access: int) -> RegistryKey:
        assert root is registry.HKEY_CURRENT_USER
        assert path == WindowsStartAtSignIn._RUN_KEY
        assert reserved == 0
        assert access == registry.KEY_SET_VALUE
        return RegistryKey()

    def set_value(key: object, name: str, reserved: int, kind: int, value: str) -> None:
        assert isinstance(key, RegistryKey)
        assert reserved == 0
        assert kind == registry.REG_SZ
        values[name] = value

    def delete_value(key: object, name: str) -> None:
        assert isinstance(key, RegistryKey)
        if name not in values:
            raise FileNotFoundError
        del values[name]

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        KEY_SET_VALUE=2,
        REG_SZ=1,
        CreateKey=create_key,
        OpenKey=open_key,
        SetValueEx=set_value,
        DeleteValue=delete_value,
    )
    monkeypatch.setattr("vellum.windows.sys.platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", registry)
    start_at_sign_in = WindowsStartAtSignIn(command='"C:\\Program Files\\Vellum\\vellum.exe"')

    start_at_sign_in.set_enabled(True)
    start_at_sign_in.set_enabled(False)
    start_at_sign_in.set_enabled(False)

    assert values == {}


def test_start_at_sign_in_command_quotes_the_executable() -> None:
    assert build_start_at_sign_in_command(r"C:\Program Files\Vellum\python.exe") == (
        '"C:\\Program Files\\Vellum\\python.exe" -m vellum.app'
    )
