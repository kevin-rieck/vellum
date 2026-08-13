from __future__ import annotations

import pytest

from vellum.windows import WindowsFocus, WindowsPaste


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
