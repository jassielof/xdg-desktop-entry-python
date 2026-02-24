"""Fixture-driven compliance tests for the Desktop Entry v1.5 implementation."""

from __future__ import annotations

import unittest
from pathlib import Path

from xdg_desktop_entry import (
    DesktopValidationError,
    deserialize,
    format_document,
    parse_desktop_entry,
    validate_document,
)

FIXTURES_ROOT = Path(__file__).parent / "fixtures"
VALID_FIXTURES = FIXTURES_ROOT / "valid"
INVALID_FIXTURES = FIXTURES_ROOT / "invalid"


def _error_codes(diags: list) -> set[str]:
    """Return only error-level diagnostic codes from a diagnostics sequence."""
    return {
        diag.code for diag in diags if getattr(diag, "severity", "error") == "error"
    }


class DesktopEntrySpecComplianceTests(unittest.TestCase):
    """Validates parser/validator behavior against curated fixture files."""

    def test_valid_fixtures_parse_and_validate(self) -> None:
        """Assert all valid fixtures parse and validate without errors."""
        files = sorted(VALID_FIXTURES.glob("*.desktop"))
        self.assertTrue(files)

        for fixture in files:
            with self.subTest(fixture=fixture.name):
                text = fixture.read_text(encoding="utf-8")
                doc, parse_diags = parse_desktop_entry(text, path=fixture)
                self.assertEqual(
                    _error_codes(parse_diags),
                    set(),
                    msg=f"Parse diagnostics for {fixture.name}: {parse_diags}",
                )

                validation_diags = validate_document(doc)
                self.assertEqual(
                    _error_codes(validation_diags),
                    set(),
                    msg=f"Validation diagnostics for {fixture.name}: {validation_diags}",
                )

    def test_invalid_fixtures_fail_parse_or_validation(self) -> None:
        """Assert invalid fixtures produce parse and/or semantic diagnostics."""
        files = sorted(INVALID_FIXTURES.glob("*.desktop"))
        self.assertTrue(files)

        for fixture in files:
            with self.subTest(fixture=fixture.name):
                text = fixture.read_text(encoding="utf-8")
                doc, parse_diags = parse_desktop_entry(text, path=fixture)
                validation_diags = validate_document(doc)

                parse_errors = _error_codes(parse_diags)
                validation_errors = _error_codes(validation_diags)
                self.assertTrue(
                    parse_errors or validation_errors,
                    msg=(
                        f"Expected errors for invalid fixture {fixture.name}; "
                        f"parse={parse_diags}, validation={validation_diags}"
                    ),
                )

    def test_roundtrip_format_and_deserialize(self) -> None:
        """Assert format -> parse roundtrip preserves semantic mapping."""
        fixture = VALID_FIXTURES / "full_entry.desktop"
        original = deserialize(
            fixture.read_text(encoding="utf-8"), path=fixture, strict=True
        )
        formatted = format_document(original)
        reparsed = deserialize(formatted, strict=True)

        self.assertEqual(original.to_mapping(), reparsed.to_mapping())

    def test_exec_validation_detects_invalid_field_code(self) -> None:
        """Assert validator reports unknown field codes in the Exec key."""
        text = """[Desktop Entry]\nType=Application\nName=Bad Exec\nExec=bad-app %Z\n"""
        doc = deserialize(text)
        diagnostics = validate_document(doc)
        self.assertIn("invalid_exec_field_code", _error_codes(diagnostics))

    def test_strict_validation_raises(self) -> None:
        """Assert strict mode raises on semantic validation failure."""
        with self.assertRaises(DesktopValidationError):
            deserialize(
                "[Desktop Entry]\nType=Application\nName=Missing Exec\n",
                strict=True,
            )


if __name__ == "__main__":
    unittest.main()
