from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping


class DesktopParseError(RuntimeError):
    """Raised when a desktop entry cannot be parsed."""


# Core value model
LocalizedValue = Dict[str, str]
ScalarValue = str
Value = ScalarValue | LocalizedValue
SectionMapping = Dict[str, Value]
DesktopMapping = Dict[str, SectionMapping]


@dataclass(slots=True)
class DesktopEntry:
    """In‑memory representation of an XDG desktop entry.

    This stays intentionally close to the Desktop Entry specification, while
    still being convenient to work with from Python. Higher‑level helpers
    (typed accessors, Exec parsing, serializers, etc.) will be layered on top.
    """

    path: Path | None
    data: DesktopMapping = field(default_factory=dict)

    def get_section(self, name: str) -> Mapping[str, Value]:
        """Return a read‑only view of a section mapping, or an empty mapping."""
        section = self.data.get(name)
        if section is None:
            return {}
        return section

    @property
    def desktop_entry(self) -> Mapping[str, Value]:
        """Convenience accessor for the main [Desktop Entry] section."""
        return self.get_section("Desktop Entry")


def _parse_desktop_text(text: str) -> DesktopMapping:
    """Parse raw desktop‑entry text into a nested mapping.

    This low‑level helper is intentionally forgiving:

    - ignores malformed lines and out‑of‑section keys
    - supports localized keys (``Key[ll]=...``)
    - strips an optional UTF‑8 BOM
    """
    data: DesktopMapping = {}
    section: str | None = None

    # Strip an optional UTF‑8 BOM on the first line; some generators include it.
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Comments and blank lines
        if not line or line.startswith("#"):
            continue

        # Section header
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            data.setdefault(section, {})
            continue

        # From here on we must be inside a section to record keys
        if section is None:
            # Technically invalid according to the spec; ignore gracefully.
            continue

        if "=" not in line:
            # Malformed line; ignore for now. We could log / collect diagnostics later.
            continue

        key_part, value = line.split("=", 1)
        key_part = key_part.strip()
        value = value.strip()

        # Localized keys: Name[fr]=..., Comment[es]=..., etc.
        if "[" in key_part and key_part.endswith("]"):
            key, locale = key_part.split("[", 1)
            locale = locale[:-1]  # drop closing ']'
            key = key.strip()

            section_dict = data.setdefault(section, {})
            existing = section_dict.get(key)

            # Normalize to a mapping of locale -> string. "C" is the implicit base.
            if isinstance(existing, dict):
                localized: LocalizedValue = existing  # type: ignore[assignment]
            elif isinstance(existing, str):
                localized = {"C": existing}
            else:
                localized = {}

            localized[locale] = value
            section_dict[key] = localized
        else:
            # Simple key=value
            section_dict = data.setdefault(section, {})
            section_dict[key_part] = value

    return data


def loads(text: str, *, path: str | Path | None = None) -> DesktopEntry:
    """Parse a desktop entry from an in‑memory string."""
    desktop_path = Path(path) if path is not None else None
    mapping = _parse_desktop_text(text)
    return DesktopEntry(path=desktop_path, data=mapping)


def load(path: str | Path) -> DesktopEntry:
    """Load an XDG desktop entry from *path*."""

    desktop_path = Path(path)
    try:
        text = desktop_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DesktopParseError(
            f"Failed to read desktop file {desktop_path!s}"
        ) from exc

    return loads(text, path=desktop_path)


from . import exec as exec  # re-export for convenience
from .desktop_file import apply_flags_to_desktop_file, sync_flags_to_desktop_file

__all__ = [
    "DesktopEntry",
    "DesktopParseError",
    "load",
    "loads",
    "exec",
    "apply_flags_to_desktop_file",
    "sync_flags_to_desktop_file",
]
