"""Public package API for parsing, validating, and formatting desktop-entry files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from . import exec as exec
from .desktop_file import (
    DesktopEntryDocument,
    DesktopEntryError,
    DesktopParseError,
    DesktopValidationError,
    Diagnostic,
    Entry,
    Section,
    check_document,
    deserialize,
    dumps,
    format_document,
    format_text,
    parse_desktop_entry,
    serialize,
    validate_document,
)
from .desktop_file import (
    load as load_document,
)

DesktopEntry = DesktopEntryDocument


def loads(
    text: str, *, path: str | Path | None = None, strict: bool = False
) -> DesktopEntry:
    """Deserialize desktop-entry text into a document model.

    Args:
        text: Raw desktop-entry file content.
        path: Optional origin path used in metadata/diagnostics.
        strict: If true, raise on parse/validation errors.

    Returns:
        Parsed desktop-entry document.
    """
    return deserialize(text, path=path, strict=strict)


def load(path: str | Path, *, strict: bool = False) -> DesktopEntry:
    """Load and deserialize a desktop-entry file from disk.

    Args:
        path: File path to read.
        strict: If true, raise on parse/validation errors.

    Returns:
        Parsed desktop-entry document.
    """
    return load_document(path, strict=strict)


def validate(entry: DesktopEntry) -> list[Diagnostic]:
    """Run semantic validation and return diagnostics."""
    return validate_document(entry)


def check(entry: DesktopEntry, *, strict: bool = False) -> list[Diagnostic]:
    """Validate a document and optionally raise on the first error."""
    return check_document(entry, strict=strict)


def from_mapping(
    mapping: Mapping[str, Mapping[str, str | Mapping[str, str]]],
    *,
    path: str | Path | None = None,
) -> DesktopEntry:
    """Construct a document from a nested section/key mapping."""
    return DesktopEntry.from_mapping(mapping, path=path)


def to_mapping(entry: DesktopEntry) -> dict[str, dict[str, str | dict[str, str]]]:
    """Convert a document into a nested section/key mapping."""
    return entry.to_mapping()


__all__ = [
    "DesktopEntry",
    "DesktopEntryDocument",
    "DesktopEntryError",
    "DesktopParseError",
    "DesktopValidationError",
    "Diagnostic",
    "Entry",
    "Section",
    "check",
    "check_document",
    "deserialize",
    "dumps",
    "exec",
    "format_document",
    "format_text",
    "from_mapping",
    "load",
    "loads",
    "parse_desktop_entry",
    "serialize",
    "to_mapping",
    "validate",
    "validate_document",
]
