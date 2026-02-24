"""
Utilities for parsing, validating, and mutating desktop-entry Exec commands.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal


class ExecParseError(ValueError):
    """Raised when an Exec command cannot be parsed."""


@dataclass(slots=True, frozen=True)
class ExecDiagnostic:
    """Diagnostic emitted by Exec command validation."""

    code: str
    message: str
    severity: Literal["error", "warning"] = "error"


class ArgumentType(Enum):
    """Token classification for parsed Exec command arguments."""

    EXECUTABLE = auto()
    LONG_FLAG = auto()  # --flag or --flag=value
    SHORT_FLAG = auto()  # -f or -f value
    FIELD_CODE = auto()  # %f, %F, %u, %U, etc.
    VALUE = auto()  # positional or value token


@dataclass(slots=True)
class ExecArgument:
    """Represents a single argument in an Exec command."""

    type: ArgumentType
    value: str
    attached_value: str | None = None  # For --flag=value

    def __str__(self) -> str:
        """Render the argument back to a shell-like string token."""
        if self.attached_value is not None:
            return f"{self.value}={self.attached_value}"
        return self.value

    def same_flag(self, other_flag: str) -> bool:
        """Compare by flag identity, ignoring attached value for long flags."""
        base = other_flag.split("=", 1)[0]
        return self.type in (ArgumentType.LONG_FLAG, ArgumentType.SHORT_FLAG) and (
            self.value == base
        )


@dataclass(slots=True)
class ExecCommand:
    """Parsed Exec command preserving argument order."""

    executable: str
    arguments: list[ExecArgument]

    def __str__(self) -> str:
        """Render command and arguments into a single command string."""
        parts = [self.executable, *(str(arg) for arg in self.arguments)]
        return " ".join(parts)

    # --- queries ---------------------------------------------------------
    def has_flag(self, flag: str) -> bool:
        """Return whether a short/long flag is present in arguments."""
        base = flag.split("=", 1)[0]
        return any(
            arg.type in (ArgumentType.LONG_FLAG, ArgumentType.SHORT_FLAG)
            and arg.value == base
            for arg in self.arguments
        )

    def enable_features(self) -> list[str]:
        """Return distinct values from all ``--enable-features=...`` flags."""
        feats: list[str] = []
        for arg in self.arguments:
            if arg.type == ArgumentType.LONG_FLAG and arg.value == "--enable-features":
                if arg.attached_value:
                    for feat in arg.attached_value.split(","):
                        if feat not in feats:
                            feats.append(feat)
        return feats

    def flag_value(self, flag: str) -> str | None:
        """Get attached or following value for a given short/long flag."""
        base = flag.split("=", 1)[0]
        for idx, arg in enumerate(self.arguments):
            if arg.type == ArgumentType.LONG_FLAG and arg.value == base:
                if arg.attached_value:
                    return arg.attached_value
                if idx + 1 < len(self.arguments):
                    nxt = self.arguments[idx + 1]
                    if nxt.type == ArgumentType.VALUE:
                        return nxt.value
                return None
            if arg.type == ArgumentType.SHORT_FLAG and arg.value == base:
                if idx + 1 < len(self.arguments):
                    nxt = self.arguments[idx + 1]
                    if nxt.type == ArgumentType.VALUE:
                        return nxt.value
                return None
        return None

    # --- mutations -------------------------------------------------------
    def add_flag(self, flag: str, *, merge_enable_features: bool = True) -> bool:
        """Insert a flag at the beginning if absent; merge enable-features."""
        if merge_enable_features and flag.startswith("--enable-features="):
            new_features = flag.split("=", 1)[1].split(",")
            existing = self.enable_features()
            to_add = [f for f in new_features if f not in existing]
            if not to_add:
                return False

            for arg in self.arguments:
                if (
                    arg.type == ArgumentType.LONG_FLAG
                    and arg.value == "--enable-features"
                ):
                    if arg.attached_value:
                        arg.attached_value = ",".join([*existing, *to_add])
                    else:
                        arg.attached_value = ",".join(to_add)
                    return True

            self.arguments.insert(0, _parse_single_argument(flag))
            return True

        if self.has_flag(flag):
            return False

        self.arguments.insert(0, _parse_single_argument(flag))
        return True

    def remove_flag(self, flag: str) -> bool:
        """Remove a flag (or feature subset for enable-features)."""
        if flag.startswith("--enable-features="):
            to_remove = set(flag.split("=", 1)[1].split(","))
            for arg in list(self.arguments):
                if (
                    arg.type == ArgumentType.LONG_FLAG
                    and arg.value == "--enable-features"
                    and arg.attached_value
                ):
                    features = arg.attached_value.split(",")
                    remaining = [f for f in features if f not in to_remove]
                    if len(remaining) != len(features):
                        if remaining:
                            arg.attached_value = ",".join(remaining)
                        else:
                            self.arguments.remove(arg)
                        return True
            return False

        base = flag.split("=", 1)[0]
        for arg in list(self.arguments):
            if (
                arg.type in (ArgumentType.LONG_FLAG, ArgumentType.SHORT_FLAG)
                and arg.value == base
            ):
                self.arguments.remove(arg)
                return True
        return False


# --- parsing helpers -----------------------------------------------------
_FIELD_CODE_RE = re.compile(r"^%[a-zA-Z]$")
_VALID_FIELD_CODES = {
    "%f",
    "%F",
    "%u",
    "%U",
    "%d",
    "%D",
    "%n",
    "%N",
    "%i",
    "%c",
    "%k",
    "%v",
    "%m",
}


def _parse_single_argument(arg: str) -> ExecArgument:
    """Convert one command token into a typed ``ExecArgument``."""
    if _FIELD_CODE_RE.match(arg):
        return ExecArgument(type=ArgumentType.FIELD_CODE, value=arg)

    if arg.startswith("--"):
        if "=" in arg:
            flag, val = arg.split("=", 1)
            return ExecArgument(ArgumentType.LONG_FLAG, flag, val)
        return ExecArgument(ArgumentType.LONG_FLAG, arg)

    if arg.startswith("-") and len(arg) >= 2 and not arg[1].isdigit():
        return ExecArgument(ArgumentType.SHORT_FLAG, arg)

    return ExecArgument(ArgumentType.VALUE, arg)


def parse_exec(exec_string: str) -> ExecCommand:
    """Parse an Exec string preserving order and typed arguments."""
    if not exec_string or not exec_string.strip():
        raise ExecParseError("Exec command string cannot be empty")

    try:
        parts = shlex.split(exec_string)
    except ValueError as exc:
        # fall back to naive split but still raise typed error
        parts = exec_string.split()
        if not parts:
            raise ExecParseError(f"Invalid Exec string: {exec_string!r}") from exc

    executable, *args = parts
    parsed_args = [_parse_single_argument(arg) for arg in args]
    return ExecCommand(executable=executable, arguments=parsed_args)


def validate_exec(exec_string: str) -> list[ExecDiagnostic]:
    """Validate an ``Exec`` command against Desktop Entry spec constraints."""
    diagnostics: list[ExecDiagnostic] = []

    if not exec_string.strip():
        diagnostics.append(
            ExecDiagnostic(code="empty_exec", message="Exec command cannot be empty")
        )
        return diagnostics

    try:
        parts = shlex.split(exec_string)
    except ValueError as exc:
        diagnostics.append(
            ExecDiagnostic(
                code="invalid_exec_quoting",
                message=f"Invalid quoting in Exec command: {exc}",
            )
        )
        return diagnostics

    if not parts:
        diagnostics.append(
            ExecDiagnostic(code="empty_exec", message="Exec command cannot be empty")
        )
        return diagnostics

    executable = parts[0]
    if "=" in executable:
        diagnostics.append(
            ExecDiagnostic(
                code="invalid_exec_executable",
                message='Executable in Exec command must not contain "="',
            )
        )

    file_open_codes = {"%f", "%F", "%u", "%U"}
    seen_open_code: str | None = None

    for arg in parts[1:]:
        if arg == "%%":
            continue

        for match in re.finditer(r"%[A-Za-z]", arg):
            code = match.group(0)
            if code not in _VALID_FIELD_CODES:
                diagnostics.append(
                    ExecDiagnostic(
                        code="invalid_exec_field_code",
                        message=f"Unknown Exec field code: {code}",
                    )
                )
                continue

            if code in file_open_codes:
                if seen_open_code is None:
                    seen_open_code = code
                elif seen_open_code != code:
                    diagnostics.append(
                        ExecDiagnostic(
                            code="multiple_open_field_codes",
                            message=(
                                "Exec command may contain at most one of %f, %F, %u, %U"
                            ),
                        )
                    )

            if code in {"%d", "%D", "%n", "%N", "%v", "%m"}:
                diagnostics.append(
                    ExecDiagnostic(
                        code="deprecated_exec_field_code",
                        message=f"Deprecated Exec field code is used: {code}",
                        severity="warning",
                    )
                )

    return diagnostics


def add_flags(
    exec_string: str, flags: Sequence[str], *, merge_enable_features: bool = True
) -> tuple[str, bool]:
    """Add flags to an Exec command while preserving command order semantics."""
    cmd = parse_exec(exec_string)
    changed = False
    for flag in flags:
        if cmd.add_flag(flag, merge_enable_features=merge_enable_features):
            changed = True
    return str(cmd), changed


def remove_flags(exec_string: str, flags: Sequence[str]) -> tuple[str, bool]:
    """Remove flags from an Exec command if present."""
    cmd = parse_exec(exec_string)
    changed = False
    for flag in flags:
        if cmd.remove_flag(flag):
            changed = True
    return str(cmd), changed


def sync_flags(
    exec_string: str,
    desired_flags: Sequence[str],
    previous_flags: Sequence[str],
    *,
    merge_enable_features: bool = True,
) -> tuple[str, bool]:
    """Remove stale previous_flags and add desired_flags."""
    cmd = parse_exec(exec_string)
    changed = False

    desired_set = set(desired_flags)
    for flag in previous_flags:
        if flag not in desired_set:
            if cmd.remove_flag(flag):
                changed = True

    for flag in desired_flags:
        if cmd.add_flag(flag, merge_enable_features=merge_enable_features):
            changed = True

    return str(cmd), changed


def merge_flags(
    flags: Iterable[str], *, merge_enable_features: bool = True
) -> list[str]:
    """Normalize and deduplicate a sequence of flags."""
    if not merge_enable_features:
        return list(dict.fromkeys(flags))

    enable_feats: list[str] = []
    others: list[str] = []
    for flag in flags:
        if flag.startswith("--enable-features="):
            feats = flag.split("=", 1)[1].split(",")
            for f in feats:
                if f not in enable_feats:
                    enable_feats.append(f)
        else:
            if flag not in others:
                others.append(flag)

    result: list[str] = []
    if enable_feats:
        result.append(f"--enable-features={','.join(enable_feats)}")
    result.extend(others)
    return result


def format_flags(flags: Iterable[str], *, merge_enable_features: bool = True) -> str:
    """Format merged flags as a single space-delimited string."""
    return " ".join(merge_flags(flags, merge_enable_features=merge_enable_features))


__all__ = [
    "ArgumentType",
    "ExecDiagnostic",
    "ExecArgument",
    "ExecCommand",
    "ExecParseError",
    "add_flags",
    "remove_flags",
    "sync_flags",
    "merge_flags",
    "format_flags",
    "parse_exec",
    "validate_exec",
]
