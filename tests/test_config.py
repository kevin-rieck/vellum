from __future__ import annotations

from vellum.config import VellumPaths


def test_vocabulary_hints_include_vellum_and_configured_domain_terms(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VELLUM_VOCABULARY_HINTS", "CTranslate2,  Acme API  ,")

    paths = VellumPaths.from_environment()

    assert paths.vocabulary_hints == ("Vellum", "CTranslate2", "Acme API")
