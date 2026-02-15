"""Desktop Entry v1.5 parser, validator, serializer, and formatter."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .exec import validate_exec

DiagnosticSeverity = Literal["error", "warning"]


@dataclass(slots=True, frozen=True)
class Diagnostic:
    """Represents a parser or validator finding."""

    code: str
    message: str
    severity: DiagnosticSeverity = "error"
    line: int | None = None


class DesktopEntryError(RuntimeError):
    """Base error for desktop-entry processing."""


class DesktopParseError(DesktopEntryError):
    """Raised when parsing fails in strict mode."""


class DesktopValidationError(DesktopEntryError):
    """Raised when validation fails in strict mode."""


@dataclass(slots=True)
class Entry:
    """Represents a single key/value record inside a section."""

    key: str
    value: str
    locale: str | None = None
    line: int | None = None

    @property
    def full_key(self) -> str:
        """Return the effective key including locale postfix when present."""
        if self.locale is None:
            return self.key
        return f"{self.key}[{self.locale}]"


@dataclass(slots=True)
class Section:
    """Represents one named section, such as ``[Desktop Entry]``."""

    name: str
    entries: list[Entry] = field(default_factory=list)

    def add(self, entry: Entry) -> None:
        """Append an entry preserving original order."""
        self.entries.append(entry)

    def iter_entries(self, key: str | None = None) -> Iterable[Entry]:
        """Iterate entries optionally filtered by base key name."""
        if key is None:
            yield from self.entries
            return
        for entry in self.entries:
            if entry.key == key:
                yield entry

    def get(self, key: str, *, locale: str | None = None) -> str | None:
        """Get key value, preferring exact locale then non-localized fallback."""
        if locale is not None:
            for entry in self.entries:
                if entry.key == key and entry.locale == locale:
                    return entry.value
        for entry in self.entries:
            if entry.key == key and entry.locale is None:
                return entry.value
        return None

    def set(self, key: str, value: str, *, locale: str | None = None) -> None:
        """Set or insert a key/value pair for the requested locale."""
        for entry in self.entries:
            if entry.key == key and entry.locale == locale:
                entry.value = value
                return
        self.entries.append(Entry(key=key, value=value, locale=locale))


@dataclass(slots=True)
class DesktopEntryDocument:
    """In-memory representation of a complete desktop-entry document."""

    sections: dict[str, Section] = field(default_factory=dict)
    path: Path | None = None

    def get_section(self, name: str) -> Section | None:
        """Return a section by name or ``None`` if it does not exist."""
        return self.sections.get(name)

    @property
    def desktop_entry(self) -> Section | None:
        """Return the canonical ``Desktop Entry`` section if present."""
        return self.get_section("Desktop Entry")

    def to_mapping(self) -> dict[str, dict[str, str | dict[str, str]]]:
        """Convert the document into nested Python dictionaries."""
        output: dict[str, dict[str, str | dict[str, str]]] = {}
        for section_name, section in self.sections.items():
            section_data: dict[str, str | dict[str, str]] = {}
            for entry in section.entries:
                if entry.locale is None:
                    section_data[entry.key] = entry.value
                    continue

                existing = section_data.get(entry.key)
                if isinstance(existing, dict):
                    localized = existing
                elif isinstance(existing, str):
                    localized = {"C": existing}
                else:
                    localized = {}
                localized[entry.locale] = entry.value
                section_data[entry.key] = localized
            output[section_name] = section_data
        return output

    @classmethod
    def from_mapping(
        cls,
        mapping: Mapping[str, Mapping[str, str | Mapping[str, str]]],
        *,
        path: str | Path | None = None,
    ) -> "DesktopEntryDocument":
        """Build a document from nested dictionaries.

        Locale dictionaries use ``"C"`` as the optional base value key.
        """
        document = cls(path=Path(path) if path is not None else None)
        for section_name, section_data in mapping.items():
            section = Section(name=section_name)
            for key, value in section_data.items():
                if isinstance(value, Mapping):
                    base = value.get("C")
                    if isinstance(base, str):
                        section.add(Entry(key=key, value=base, locale=None))
                    for locale, localized_value in value.items():
                        if locale == "C":
                            continue
                        section.add(
                            Entry(
                                key=key, value=str(localized_value), locale=str(locale)
                            )
                        )
                else:
                    section.add(Entry(key=key, value=str(value), locale=None))
            document.sections[section_name] = section
        return document


_GROUP_NAME_RE = re.compile(r"^[^\x00-\x1f\x7f\[\]]+$")
_KEY_RE = re.compile(
    r"^(?P<key>[A-Za-z0-9-]+)(?:\[(?P<locale>[^\]\x00-\x1f\x7f]+)\])?$"
)
_LOCALE_RE = re.compile(
    r"^[A-Za-z]{2,}(?:_[A-Za-z0-9]{2,})?(?:\.[A-Za-z0-9_-]+)?(?:@[A-Za-z0-9_-]+)?$"
)
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


@dataclass(slots=True, frozen=True)
class KeySpec:
    """Descriptor for a recognized standard key and its constraints."""

    value_type: str
    allowed_types: frozenset[str]


_STANDARD_KEYS: dict[str, KeySpec] = {
    "Type": KeySpec("string", frozenset({"Application", "Link", "Directory"})),
    "Version": KeySpec("string", frozenset({"Application", "Link", "Directory"})),
    "Name": KeySpec("localestring", frozenset({"Application", "Link", "Directory"})),
    "GenericName": KeySpec(
        "localestring", frozenset({"Application", "Link", "Directory"})
    ),
    "NoDisplay": KeySpec("boolean", frozenset({"Application", "Link", "Directory"})),
    "Comment": KeySpec("localestring", frozenset({"Application", "Link", "Directory"})),
    "Icon": KeySpec("iconstring", frozenset({"Application", "Link", "Directory"})),
    "Hidden": KeySpec("boolean", frozenset({"Application", "Link", "Directory"})),
    "OnlyShowIn": KeySpec("string(s)", frozenset({"Application", "Link", "Directory"})),
    "NotShowIn": KeySpec("string(s)", frozenset({"Application", "Link", "Directory"})),
    "DBusActivatable": KeySpec(
        "boolean", frozenset({"Application", "Link", "Directory"})
    ),
    "TryExec": KeySpec("string", frozenset({"Application"})),
    "Exec": KeySpec("string", frozenset({"Application"})),
    "Path": KeySpec("string", frozenset({"Application"})),
    "Terminal": KeySpec("boolean", frozenset({"Application"})),
    "Actions": KeySpec("string(s)", frozenset({"Application"})),
    "MimeType": KeySpec("string(s)", frozenset({"Application"})),
    "Categories": KeySpec("string(s)", frozenset({"Application"})),
    "Implements": KeySpec("string(s)", frozenset({"Application", "Link", "Directory"})),
    "Keywords": KeySpec("localestring(s)", frozenset({"Application"})),
    "StartupNotify": KeySpec("boolean", frozenset({"Application"})),
    "StartupWMClass": KeySpec("string", frozenset({"Application"})),
    "URL": KeySpec("string", frozenset({"Link"})),
    "PrefersNonDefaultGPU": KeySpec("boolean", frozenset({"Application"})),
    "SingleMainWindow": KeySpec("boolean", frozenset({"Application"})),
}


def _unescape_value(value: str) -> str:
    """Decode Desktop Entry escape sequences in a scalar value."""
    result: list[str] = []
    index = 0
    length = len(value)
    while index < length:
        char = value[index]
        if char != "\\" or index + 1 >= length:
            result.append(char)
            index += 1
            continue

        nxt = value[index + 1]
        if nxt == "s":
            result.append(" ")
        elif nxt == "n":
            result.append("\n")
        elif nxt == "t":
            result.append("\t")
        elif nxt == "r":
            result.append("\r")
        elif nxt == "\\":
            result.append("\\")
        elif nxt == ";":
            result.append(";")
        else:
            result.append(nxt)
        index += 2
    return "".join(result)


def _escape_value(value: str) -> str:
    """Encode Desktop Entry escape sequences in a scalar value."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace(";", "\\;")
    )
    return escaped


def _split_list(value: str) -> list[str]:
    """Split a semicolon-delimited value list honoring escaped separators."""
    items: list[str] = []
    current: list[str] = []
    escaped = False

    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            current.append(char)
            continue
        if char == ";":
            part = "".join(current)
            if part:
                items.append(_unescape_value(part))
            current = []
            continue
        current.append(char)

    tail = "".join(current)
    if tail:
        items.append(_unescape_value(tail))
    return items


def parse_desktop_entry(
    text: str,
    *,
    path: str | Path | None = None,
    strict: bool = False,
) -> tuple[DesktopEntryDocument, list[Diagnostic]]:
    """Parse desktop-entry text into a document and parse diagnostics.

    Args:
        text: Raw text content of a desktop file.
        path: Optional source path attached to the document.
        strict: If true, raise on first parse error.

    Returns:
        Tuple of parsed document and parse diagnostics.
    """
    if text.startswith("\ufeff"):
        text = text[1:]

    diagnostics: list[Diagnostic] = []
    document = DesktopEntryDocument(path=Path(path) if path is not None else None)

    current_section: Section | None = None
    first_group_seen: str | None = None

    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("["):
            if not line.endswith("]"):
                diagnostics.append(
                    Diagnostic(
                        code="invalid_group_header",
                        message="Group header is missing closing ']'",
                        line=line_number,
                    )
                )
                continue

            group_name = line[1:-1]
            if not group_name:
                diagnostics.append(
                    Diagnostic(
                        code="invalid_group_header",
                        message="Group header cannot be empty",
                        line=line_number,
                    )
                )
                continue

            if not _GROUP_NAME_RE.match(group_name):
                diagnostics.append(
                    Diagnostic(
                        code="invalid_group_name",
                        message=f"Invalid group name: {group_name!r}",
                        line=line_number,
                    )
                )
                continue

            if group_name in document.sections:
                diagnostics.append(
                    Diagnostic(
                        code="duplicate_group",
                        message=f"Duplicate group: [{group_name}]",
                        line=line_number,
                    )
                )
                current_section = document.sections[group_name]
                continue

            current_section = Section(name=group_name)
            document.sections[group_name] = current_section
            if first_group_seen is None:
                first_group_seen = group_name
            continue

        if "=" not in line:
            diagnostics.append(
                Diagnostic(
                    code="invalid_line_format",
                    message="Entry lines must be in the form Key=Value",
                    line=line_number,
                )
            )
            continue

        if current_section is None:
            diagnostics.append(
                Diagnostic(
                    code="entry_before_group",
                    message="Entry appears before first group header",
                    line=line_number,
                )
            )
            continue

        key_part, value_part = line.split("=", 1)
        key_part = key_part.strip()
        value_part = value_part.strip()

        key_match = _KEY_RE.match(key_part)
        if key_match is None:
            diagnostics.append(
                Diagnostic(
                    code="invalid_key_name",
                    message=f"Invalid key name: {key_part!r}",
                    line=line_number,
                )
            )
            continue

        key = key_match.group("key")
        locale = key_match.group("locale")

        if locale is not None and not _LOCALE_RE.match(locale):
            diagnostics.append(
                Diagnostic(
                    code="invalid_locale",
                    message=f"Invalid locale postfix: [{locale}]",
                    line=line_number,
                )
            )

        full_key = key if locale is None else f"{key}[{locale}]"
        duplicate = any(
            existing.full_key == full_key for existing in current_section.entries
        )
        if duplicate:
            diagnostics.append(
                Diagnostic(
                    code="duplicate_key",
                    message=f"Duplicate key in section [{current_section.name}]: {full_key}",
                    line=line_number,
                )
            )
            continue

        current_section.add(
            Entry(
                key=key,
                locale=locale,
                value=_unescape_value(value_part),
                line=line_number,
            )
        )

    if first_group_seen is not None and first_group_seen != "Desktop Entry":
        diagnostics.append(
            Diagnostic(
                code="desktop_entry_not_first",
                message="The first group must be [Desktop Entry] (ignoring comments and blanks)",
            )
        )

    if strict and any(item.severity == "error" for item in diagnostics):
        first = next(item for item in diagnostics if item.severity == "error")
        where = f" (line {first.line})" if first.line is not None else ""
        raise DesktopParseError(f"{first.code}: {first.message}{where}")

    return document, diagnostics


def _is_true(value: str | None) -> bool:
    """Return whether a value is exactly the desktop-entry ``true`` literal."""
    return value == "true"


def _validate_value_type(value_type: str, value: str) -> bool:
    """Check a raw value against a declared desktop-entry value type."""
    if value_type == "boolean":
        return value in {"true", "false"}
    if value_type == "numeric":
        return bool(_FLOAT_RE.match(value))
    if value_type in {"string(s)", "localestring(s)", "iconstring(s)"}:
        _split_list(value)
        return True
    return True


def validate_document(document: DesktopEntryDocument) -> list[Diagnostic]:
    """Run semantic validation for a parsed desktop-entry document."""
    diagnostics: list[Diagnostic] = []

    desktop = document.desktop_entry
    if desktop is None:
        diagnostics.append(
            Diagnostic(
                code="missing_desktop_entry",
                message="Missing required [Desktop Entry] group",
            )
        )
        return diagnostics

    entry_type = desktop.get("Type")
    if entry_type is None:
        diagnostics.append(
            Diagnostic(
                code="missing_type",
                message="Missing required key Type in [Desktop Entry]",
            )
        )
        return diagnostics

    if entry_type not in {"Application", "Link", "Directory"}:
        diagnostics.append(
            Diagnostic(
                code="invalid_type",
                message=f"Invalid Type value: {entry_type!r}",
                line=next((item.line for item in desktop.iter_entries("Type")), None),
            )
        )
        return diagnostics

    if desktop.get("Name") is None:
        diagnostics.append(
            Diagnostic(
                code="missing_name",
                message="Missing required key Name in [Desktop Entry]",
            )
        )

    if entry_type == "Link" and desktop.get("URL") is None:
        diagnostics.append(
            Diagnostic(
                code="missing_url",
                message="Missing required key URL for Type=Link",
            )
        )

    if entry_type == "Application":
        dbus_activatable = _is_true(desktop.get("DBusActivatable"))
        if desktop.get("Exec") is None and not dbus_activatable:
            diagnostics.append(
                Diagnostic(
                    code="missing_exec",
                    message="Missing required key Exec for Type=Application when DBusActivatable is not true",
                )
            )

    for section in document.sections.values():
        localized_keys: dict[str, bool] = {}
        base_keys: set[str] = set()

        for entry in section.entries:
            if entry.locale is None:
                base_keys.add(entry.key)
            else:
                localized_keys[entry.key] = True

            if section.name == "Desktop Entry":
                spec = _STANDARD_KEYS.get(entry.key)
                if spec is not None:
                    if entry_type not in spec.allowed_types:
                        diagnostics.append(
                            Diagnostic(
                                code="key_not_allowed_for_type",
                                message=(
                                    f"Key {entry.key!r} is not allowed for Type={entry_type}"
                                ),
                                line=entry.line,
                            )
                        )
                    if not _validate_value_type(spec.value_type, entry.value):
                        diagnostics.append(
                            Diagnostic(
                                code="invalid_value_type",
                                message=(
                                    f"Invalid value for key {entry.key!r}; expected {spec.value_type}"
                                ),
                                line=entry.line,
                            )
                        )

                    if spec.value_type == "boolean" and entry.value not in {
                        "true",
                        "false",
                    }:
                        diagnostics.append(
                            Diagnostic(
                                code="invalid_boolean",
                                message=f"Boolean key {entry.key!r} must be 'true' or 'false'",
                                line=entry.line,
                            )
                        )

            if entry.key == "Exec":
                for exec_diag in validate_exec(entry.value):
                    diagnostics.append(
                        Diagnostic(
                            code=exec_diag.code,
                            message=exec_diag.message,
                            line=entry.line,
                            severity=exec_diag.severity,
                        )
                    )

        for key in localized_keys:
            if key not in base_keys:
                diagnostics.append(
                    Diagnostic(
                        code="localized_without_base",
                        message=f"Localized key {key}[...] must have a non-localized base key",
                    )
                )

    only_show = desktop.get("OnlyShowIn")
    not_show = desktop.get("NotShowIn")
    if only_show and not_show:
        overlap = set(_split_list(only_show)).intersection(_split_list(not_show))
        if overlap:
            diagnostics.append(
                Diagnostic(
                    code="showin_conflict",
                    message=(
                        "OnlyShowIn and NotShowIn contain overlapping desktops: "
                        + ", ".join(sorted(overlap))
                    ),
                )
            )

    actions_raw = desktop.get("Actions")
    if actions_raw:
        action_ids = [item for item in _split_list(actions_raw) if item]
        for action_id in action_ids:
            group_name = f"Desktop Action {action_id}"
            group = document.get_section(group_name)
            if group is None:
                diagnostics.append(
                    Diagnostic(
                        code="missing_action_group",
                        message=f"Missing required action group [{group_name}]",
                    )
                )
                continue
            if group.get("Name") is None:
                diagnostics.append(
                    Diagnostic(
                        code="missing_action_name",
                        message=f"Action group [{group_name}] must contain Name",
                    )
                )
            if group.get("Exec") is None:
                diagnostics.append(
                    Diagnostic(
                        code="missing_action_exec",
                        message=f"Action group [{group_name}] must contain Exec",
                    )
                )

    return diagnostics


def check_document(
    document: DesktopEntryDocument, *, strict: bool = False
) -> list[Diagnostic]:
    """Validate a document and optionally raise on first error diagnostic."""
    diagnostics = validate_document(document)
    if strict and any(item.severity == "error" for item in diagnostics):
        first = next(item for item in diagnostics if item.severity == "error")
        where = f" (line {first.line})" if first.line is not None else ""
        raise DesktopValidationError(f"{first.code}: {first.message}{where}")
    return diagnostics


def deserialize(
    text: str,
    *,
    path: str | Path | None = None,
    strict: bool = False,
) -> DesktopEntryDocument:
    """Parse text and optionally enforce strict validation."""
    document, parse_diagnostics = parse_desktop_entry(text, path=path, strict=strict)
    if strict and parse_diagnostics:
        return document
    if strict:
        check_document(document, strict=True)
    return document


def load(path: str | Path, *, strict: bool = False) -> DesktopEntryDocument:
    """Load, parse, and optionally strictly validate a desktop-entry file."""
    desktop_path = Path(path)
    try:
        text = desktop_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DesktopParseError(f"Failed to read desktop file {desktop_path}") from exc
    return deserialize(text, path=desktop_path, strict=strict)


def dumps(
    document: DesktopEntryDocument,
    *,
    sort_sections: bool = False,
    sort_entries: bool = False,
    trailing_newline: bool = True,
) -> str:
    """Serialize a document back to desktop-entry text."""
    section_names = list(document.sections)
    if sort_sections:
        if "Desktop Entry" in document.sections:
            section_names = ["Desktop Entry"] + sorted(
                name for name in document.sections if name != "Desktop Entry"
            )
        else:
            section_names = sorted(section_names)

    lines: list[str] = []
    for idx, section_name in enumerate(section_names):
        section = document.sections[section_name]
        if idx > 0:
            lines.append("")
        lines.append(f"[{section.name}]")

        entries = list(section.entries)
        if sort_entries:
            entries.sort(
                key=lambda item: (item.key, "" if item.locale is None else item.locale)
            )

        for entry in entries:
            key = entry.key if entry.locale is None else f"{entry.key}[{entry.locale}]"
            lines.append(f"{key}={_escape_value(entry.value)}")

    text = "\n".join(lines)
    if trailing_newline:
        text += "\n"
    return text


def serialize(
    mapping: Mapping[str, Mapping[str, str | Mapping[str, str]]],
    *,
    sort_sections: bool = False,
    sort_entries: bool = False,
    trailing_newline: bool = True,
) -> str:
    """Serialize a nested mapping into desktop-entry text."""
    document = DesktopEntryDocument.from_mapping(mapping)
    return dumps(
        document,
        sort_sections=sort_sections,
        sort_entries=sort_entries,
        trailing_newline=trailing_newline,
    )


def format_document(
    document: DesktopEntryDocument,
    *,
    sort_sections: bool = True,
    sort_entries: bool = True,
) -> str:
    """Format a document into deterministic, human-readable text."""
    return dumps(
        document,
        sort_sections=sort_sections,
        sort_entries=sort_entries,
        trailing_newline=True,
    )


def format_text(text: str, *, strict: bool = False) -> str:
    """Parse and format text in one step."""
    document = deserialize(text, strict=strict)
    return format_document(document)


__all__ = [
    "Diagnostic",
    "DesktopEntryDocument",
    "DesktopEntryError",
    "DesktopParseError",
    "DesktopValidationError",
    "Entry",
    "Section",
    "check_document",
    "deserialize",
    "dumps",
    "format_document",
    "format_text",
    "load",
    "parse_desktop_entry",
    "serialize",
    "validate_document",
]
