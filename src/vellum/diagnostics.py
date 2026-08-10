"""Local diagnostics for failures that occur after the tray application starts."""

from __future__ import annotations

import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER = logging.getLogger("vellum")
_CONSOLE_FORMATTER = logging.Formatter("%(asctime)s %(levelname)s %(message)s")


class _DiagnosticFileFormatter(logging.Formatter):
    """Formats local diagnostics without persisting exception messages."""

    def format(self, record: logging.LogRecord) -> str:
        exception_type = record.exc_info[0] if record.exc_info else None
        exception_name = exception_type.__name__ if exception_type else "UnknownError"
        rendered = f"{self.formatTime(record)} {record.levelname} Vellum error ({exception_name})"
        if record.exc_info and record.exc_info[2]:
            frames = "".join(traceback.format_tb(record.exc_info[2])).rstrip()
            if frames:
                return f"{rendered}\n{frames}"
        return rendered


def configure_diagnostics(log_file: Path) -> None:
    """Send Vellum errors to stderr and a bounded local log file.

    The log contains exception types and stack frames only; it does not record
    audio or Transcripts.
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
        file_handler = RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=1, encoding="utf-8"
        )
    except OSError:
        LOGGER.exception("Vellum could not create its diagnostics log at %s.", log_file)
        return

    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(_DiagnosticFileFormatter())
    LOGGER.addHandler(file_handler)


def log_error(error: Exception) -> None:
    """Write a detailed console error and a private, stack-only local diagnostic."""
    LOGGER.error(
        "Vellum error: %s", error, exc_info=(type(error), error, error.__traceback__)
    )


def _remove_existing_handlers() -> None:
    for handler in LOGGER.handlers:
        LOGGER.removeHandler(handler)
        handler.close()
