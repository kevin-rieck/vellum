"""Redacted, local-only diagnostics for failures after the tray starts."""

from __future__ import annotations

import logging
import platform
import re
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from vellum import __version__

LOGGER = logging.getLogger("vellum")
_RECORD_PATTERN = re.compile(
    r"^\S+ \S+ \S+ Vellum diagnostic "
    r"\(category=([a-z0-9-]+), exception=([A-Za-z_][A-Za-z0-9_.]*)\)$"
)
_STACK_PATTERN = re.compile(r"^  at ([A-Za-z_][A-Za-z0-9_.<>]*) \(line (\d+)\)$")
_CATEGORY_PATTERN = re.compile(r"^[a-z0-9-]{1,32}$")


class _RedactedFormatter(logging.Formatter):
    """Allowlist diagnostic fields and never render a log message or file path."""

    def format(self, record: logging.LogRecord) -> str:
        exception_type = record.exc_info[0] if record.exc_info else None
        exception_name = _safe_name(
            exception_type.__name__ if exception_type is not None else "UnknownError"
        )
        category = _safe_category(getattr(record, "diagnostic_category", "error"))
        rendered = (
            f"{self.formatTime(record)} {record.levelname} Vellum diagnostic "
            f"(category={category}, exception={exception_name})"
        )
        if record.exc_info and record.exc_info[2]:
            # TracebackSummary deliberately omits source paths and source-code lines.
            frames = traceback.extract_tb(record.exc_info[2])
            rendered += "".join(
                f"\n  at {_safe_name(frame.name)} (line {frame.lineno})"
                for frame in frames[-20:]
            )
        return rendered


# Kept as a private compatibility name for callers that used the original formatter in tests.
_DiagnosticFileFormatter = _RedactedFormatter
_CONSOLE_FORMATTER = _RedactedFormatter()


def configure_diagnostics(log_file: Path) -> None:
    """Send allowlisted diagnostics to stderr and a bounded local log file.

    Diagnostics are never uploaded, and this function performs no network operation.
    Exception messages, settings, paths, audio, Transcripts, and clipboard contents are
    intentionally not included in either output stream.
    """
    LOGGER.setLevel(logging.ERROR)
    LOGGER.propagate = False
    _remove_existing_handlers()

    console = logging.StreamHandler()
    console.setLevel(logging.ERROR)
    console.setFormatter(_CONSOLE_FORMATTER)
    LOGGER.addHandler(console)

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Start a fresh file so a pre-release log cannot remain a source of
        # unredacted paths or messages after an upgrade. Remove its one old
        # rotation as well; it is part of the local diagnostics surface.
        log_file.unlink(missing_ok=True)
        log_file.with_name(f"{log_file.name}.1").unlink(missing_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=1, encoding="utf-8", mode="w"
        )
    except OSError:
        LOGGER.exception(
            "Vellum could not create its diagnostics log", extra={"diagnostic_category": "logging"}
        )
        return

    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(_DiagnosticFileFormatter())
    LOGGER.addHandler(file_handler)


def log_error(error: Exception, *, category: str = "error") -> None:
    """Write a redacted diagnostic for an error to the local log and console."""
    LOGGER.error(
        "Vellum diagnostic",  # The formatter intentionally discards this message.
        exc_info=(type(error), error, error.__traceback__),
        extra={"diagnostic_category": category},
    )


def build_redacted_diagnostics(log_file: Path) -> str:
    """Build a safe, user-copyable diagnostic snapshot from the local log.

    Existing files are parsed through an allowlist so a log produced by an older
    Vellum version cannot leak a message or path when the user copies diagnostics.
    """
    lines = [
        "Vellum redacted diagnostics",
        f"version: {__version__}",
        f"platform: {sys.platform}",
        f"python: {platform.python_version()}",
        "automatic upload: disabled",
        "",
    ]
    events: list[str] = []
    try:
        raw_lines = log_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        raw_lines = []

    for line in raw_lines:
        record_match = _RECORD_PATTERN.match(line)
        if record_match:
            events.append(
                f"error category: {record_match.group(1)}; "
                f"exception: {record_match.group(2)}"
            )
            continue
        stack_match = _STACK_PATTERN.match(line)
        if stack_match:
            events.append(f"  at {stack_match.group(1)} (line {stack_match.group(2)})")

    if events:
        lines.extend(events)
    else:
        lines.append("No diagnostic events are available.")
    return "\n".join(lines) + "\n"


# A concise alias reads naturally at the UI seam and keeps the public function discoverable.
redacted_diagnostics = build_redacted_diagnostics


def _safe_category(value: object) -> str:
    if isinstance(value, str) and _CATEGORY_PATTERN.fullmatch(value):
        return value
    return "error"


def _safe_name(value: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.<>]", "_", value)
    return safe_name[:80] or "unknown"


def _remove_existing_handlers() -> None:
    for handler in LOGGER.handlers:
        LOGGER.removeHandler(handler)
        handler.close()
