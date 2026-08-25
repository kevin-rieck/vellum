"""Vellum, a local Windows dictation application."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vellum")
except PackageNotFoundError:
    # Source checkout fallback; the packaged distribution supplies its metadata.
    __version__ = "0.1.0"
