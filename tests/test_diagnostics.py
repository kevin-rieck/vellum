from __future__ import annotations

import logging
from pathlib import Path

from vellum.diagnostics import (
    build_redacted_diagnostics,
    configure_diagnostics,
    log_error,
)


def test_diagnostics_exclude_exception_messages_and_user_paths(tmp_path: Path) -> None:
    log_file = tmp_path / "Vellum" / "vellum.log"
    configure_diagnostics(log_file)
    try:
        try:
            raise RuntimeError("transcript secret C:/Users/Alice/private.txt")
        except RuntimeError as error:
            log_error(error)

        contents = log_file.read_text(encoding="utf-8")
        snapshot = build_redacted_diagnostics(log_file)
    finally:
        logging.getLogger("vellum").handlers.clear()

    assert "transcript secret" not in contents
    assert "C:/Users/Alice" not in contents
    assert "RuntimeError" in contents
    assert "transcript secret" not in snapshot
    assert "C:/Users/Alice" not in snapshot
    assert "RuntimeError" in snapshot
    assert "automatic upload: disabled" in snapshot


def test_redacted_diagnostics_ignore_untrusted_existing_log_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "vellum.log"
    log_file.write_text("user transcript and C:/Users/Alice/secret.txt\n", encoding="utf-8")

    snapshot = build_redacted_diagnostics(log_file)

    assert "user transcript" not in snapshot
    assert "C:/Users/Alice" not in snapshot
    assert "No diagnostic events" in snapshot


def test_configuring_diagnostics_removes_legacy_log_and_rotation(
    tmp_path: Path,
) -> None:
    log_file = tmp_path / "vellum.log"
    backup_file = tmp_path / "vellum.log.1"
    log_file.write_text("legacy path C:/Users/Alice/secret.txt\n", encoding="utf-8")
    backup_file.write_text("legacy transcript\n", encoding="utf-8")

    configure_diagnostics(log_file)
    try:
        assert log_file.read_text(encoding="utf-8") == ""
        assert not backup_file.exists()
    finally:
        logging.getLogger("vellum").handlers.clear()
