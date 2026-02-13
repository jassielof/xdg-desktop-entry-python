from __future__ import annotations

import configparser
import io
from pathlib import Path
from typing import Sequence

from . import DesktopParseError, load as load_entry, loads as loads_entry
from .exec import add_flags as add_flags_to_exec, sync_flags as sync_flags_in_exec


def apply_flags_to_desktop_file(
    path: Path | str,
    flags: Sequence[str],
    *,
    merge_enable_features: bool = True,
) -> tuple[str, bool]:
    """Apply flags to all Exec keys in a .desktop file."""
    desktop_path = Path(path)
    entry = load_entry(desktop_path)

    parser = configparser.ConfigParser(
        delimiters=("=",),
        interpolation=None,
        allow_no_value=True,
    )
    parser.optionxform = str

    try:
        content = desktop_path.read_text()
    except (IOError, UnicodeDecodeError) as exc:
        raise DesktopParseError(f"Cannot read desktop file {desktop_path}: {exc}") from exc

    shebang = None
    if content.startswith("#!"):
        lines = content.splitlines()
        shebang = lines[0]
        content = "\n".join(lines[1:])

    parser.read_string(content)

    any_modified = False
    for section in parser.sections():
        if parser.has_option(section, "Exec"):
            original = parser.get(section, "Exec")
            modified_exec, was_modified = add_flags_to_exec(
                original, flags, merge_enable_features=merge_enable_features
            )
            if was_modified:
                parser.set(section, "Exec", modified_exec)
                any_modified = True

    string_io = io.StringIO()
    parser.write(string_io, space_around_delimiters=False)
    result = string_io.getvalue().strip()

    if shebang:
        result = f"{shebang}\n{result}"

    return result, any_modified


def sync_flags_to_desktop_file(
    user_path: Path | str,
    system_path: Path | str,
    desired_flags: Sequence[str],
    previous_flags: Sequence[str],
    *,
    merge_enable_features: bool = True,
) -> tuple[str, bool]:
    """Regenerate a user desktop file from the system baseline and sync flags."""
    user_path = Path(user_path)
    system_path = Path(system_path)

    source_path = system_path if system_path.exists() else user_path
    if not source_path.exists():
        raise FileNotFoundError(f"Neither {user_path} nor {system_path} found")

    base_entry = load_entry(source_path)

    parser = configparser.ConfigParser(
        delimiters=("=",),
        interpolation=None,
        allow_no_value=True,
    )
    parser.optionxform = str

    try:
        content = source_path.read_text()
    except (IOError, UnicodeDecodeError) as exc:
        raise DesktopParseError(f"Cannot read desktop file {source_path}: {exc}") from exc

    shebang = None
    if content.startswith("#!"):
        lines = content.splitlines()
        shebang = lines[0]
        content = "\n".join(lines[1:])

    parser.read_string(content)

    any_modified = False
    for section in parser.sections():
        if parser.has_option(section, "Exec"):
            original = parser.get(section, "Exec")
            modified_exec, was_modified = sync_flags_in_exec(
                original,
                desired_flags,
                previous_flags,
                merge_enable_features=merge_enable_features,
            )
            if was_modified:
                parser.set(section, "Exec", modified_exec)
                any_modified = True

    string_io = io.StringIO()
    parser.write(string_io, space_around_delimiters=False)
    result = string_io.getvalue().strip()

    if shebang:
        result = f"{shebang}\n{result}"

    # Compare with current user content if exists
    if user_path.exists():
        try:
            current_content = user_path.read_text().strip()
            any_modified = any_modified or (result.strip() != current_content)
        except (IOError, UnicodeDecodeError):
            any_modified = True
    else:
        any_modified = True

    return result, any_modified


__all__ = [
    "apply_flags_to_desktop_file",
    "sync_flags_to_desktop_file",
]


