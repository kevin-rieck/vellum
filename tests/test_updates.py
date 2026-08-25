from __future__ import annotations

import io

import pytest

from vellum.updates import (
    UpdateChecker,
    UpdateCheckError,
    UpdateStatus,
    parse_release_metadata,
)


def test_update_check_is_explicit_and_reports_a_new_release() -> None:
    calls: list[tuple[object, float]] = []

    def opener(request: object, timeout: float) -> io.BytesIO:
        calls.append((request, timeout))
        return io.BytesIO(b'{"tag_name":"v0.2.0","html_url":"https://example.test/vellum"}')

    checker = UpdateChecker("0.1.0", opener=opener)

    result = checker.check()

    assert result.status is UpdateStatus.UPDATE_AVAILABLE
    assert result.release is not None
    assert result.release.version == "0.2.0"
    assert result.release.url == "https://example.test/vellum"
    assert len(calls) == 1
    assert calls[0][1] == 10.0


def test_update_check_does_not_call_the_network_until_check_is_requested() -> None:
    calls: list[object] = []
    def opener(request: object, timeout: float) -> io.BytesIO:
        calls.append(request)
        return io.BytesIO(b'{"tag_name":"v0.2.0","html_url":"https://example.test/vellum"}')

    checker = UpdateChecker("0.2.0", opener=opener)

    assert calls == []
    result = checker.check()

    assert result.status is UpdateStatus.UP_TO_DATE
    assert calls != []


def test_update_metadata_rejects_non_https_release_links() -> None:
    with pytest.raises(UpdateCheckError, match="HTTPS"):
        parse_release_metadata(
            {"tag_name": "v0.2.0", "html_url": "http://example.test/vellum"}
        )


def test_update_metadata_rejects_malformed_versions() -> None:
    with pytest.raises(UpdateCheckError):
        parse_release_metadata({"tag_name": "latest", "html_url": "https://example.test"})


def test_update_check_hides_transport_details_from_the_user_error() -> None:
    def opener(_request: object, _timeout: float) -> object:
        raise OSError("secret user path and transcript")

    with pytest.raises(UpdateCheckError, match="could not be completed") as raised:
        UpdateChecker("0.1.0", opener=opener).check()

    assert "secret" not in str(raised.value)
    assert "transcript" not in str(raised.value)


def test_update_endpoint_must_be_https() -> None:
    with pytest.raises(UpdateCheckError, match="HTTPS"):
        UpdateChecker("0.1.0", metadata_url="http://example.test/releases")
