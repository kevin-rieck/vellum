"""Explicit, read-only release discovery for the Vellum tray application."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_UPDATE_METADATA_URL = "https://api.github.com/repos/kevin-rieck/vellum/releases/latest"
_UPDATE_TIMEOUT_SECONDS = 10.0
_MAX_METADATA_BYTES = 64 * 1024
_VERSION_PATTERN = re.compile(r"^(?:v)?(\d+)(?:\.(\d+))(?:\.(\d+))(?:[-+][0-9A-Za-z.-]+)?$")


class UpdateCheckError(RuntimeError):
    """Raised when the user-requested release check cannot be trusted or completed."""


class UpdateStatus(Enum):
    """The result of comparing the installed release with the latest release."""

    UP_TO_DATE = "up-to-date"
    UPDATE_AVAILABLE = "update-available"


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """A release link that the user may choose to open and install."""

    version: str
    url: str


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """A user-requested update comparison; Vellum never downloads this release."""

    status: UpdateStatus
    current_version: str
    release: ReleaseInfo | None = None


class UrlOpener(Protocol):
    def __call__(self, request: Request, timeout: float) -> Any: ...


def _normalise_version(value: object) -> tuple[str, tuple[int, int, int]]:
    if not isinstance(value, str):
        raise UpdateCheckError("The release metadata did not contain a supported version.")
    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise UpdateCheckError("The release metadata did not contain a supported version.")
    parsed_numbers = tuple(int(part) for part in match.groups())
    numbers = (parsed_numbers[0], parsed_numbers[1], parsed_numbers[2])
    return ".".join(str(number) for number in numbers), numbers


def parse_release_metadata(value: object) -> ReleaseInfo:
    """Parse and validate the small public release contract used by update discovery."""
    if not isinstance(value, dict):
        raise UpdateCheckError("The release metadata was not a JSON object.")

    version_value = value.get("tag_name", value.get("version"))
    version, _ = _normalise_version(version_value)
    url = value.get("html_url", value.get("release_url", value.get("url")))
    if not isinstance(url, str) or not url.startswith("https://"):
        raise UpdateCheckError("The release metadata did not contain an HTTPS release link.")
    return ReleaseInfo(version=version, url=url)


class UpdateChecker:
    """Checks a trusted HTTPS release endpoint only when :meth:`check` is called."""

    def __init__(
        self,
        current_version: str,
        *,
        metadata_url: str = DEFAULT_UPDATE_METADATA_URL,
        opener: UrlOpener | None = None,
        timeout: float = _UPDATE_TIMEOUT_SECONDS,
    ) -> None:
        normalised_current, current_parts = _normalise_version(current_version)
        if not metadata_url.startswith("https://"):
            raise UpdateCheckError("The update metadata endpoint must use HTTPS.")
        if timeout <= 0 or timeout > 60:
            raise ValueError("The update check timeout must be greater than zero and at most 60s.")
        self._current_version = normalised_current
        self._current_parts = current_parts
        self._metadata_url = metadata_url
        self._opener: UrlOpener = opener or (
            lambda request, timeout: urlopen(request, timeout=timeout)
        )
        self._timeout = timeout

    @property
    def metadata_url(self) -> str:
        return self._metadata_url

    def check(self) -> UpdateResult:
        """Fetch release metadata for a user action; no call happens during construction."""
        request = Request(
            self._metadata_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Vellum update checker",
            },
        )
        try:
            with self._opener(request, self._timeout) as response:
                response_url = (
                    response.geturl() if hasattr(response, "geturl") else self._metadata_url
                )
                if not isinstance(response_url, str) or not response_url.startswith("https://"):
                    raise UpdateCheckError(
                        "The update metadata response was not delivered over HTTPS."
                    )
                payload = response.read(_MAX_METADATA_BYTES + 1)
            if len(payload) > _MAX_METADATA_BYTES:
                raise UpdateCheckError("The update metadata response was too large.")
            metadata = json.loads(payload.decode("utf-8"))
            release = parse_release_metadata(metadata)
        except UpdateCheckError:
            raise
        except (HTTPError, URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise UpdateCheckError("The update check could not be completed.") from error

        _, release_parts = _normalise_version(release.version)
        if release_parts <= self._current_parts:
            return UpdateResult(UpdateStatus.UP_TO_DATE, self._current_version)
        return UpdateResult(UpdateStatus.UPDATE_AVAILABLE, self._current_version, release)
