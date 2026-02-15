# XDG Desktop Entry for Python

XDG Desktop file format library for Python.

## Features

- Desktop Entry Specification v1.5 focused parser/deserializer
- Validator/checker for parse + semantic rules (required keys, types, actions, `Exec` field-codes)
- Serializer + formatter for deterministic output
- Localized key support (`Name[es]`, `Comment[fr]`, etc.)
- Pure Python stdlib (Python 3.14+)

## Quick usage

```python
from xdg_desktop_entry import load, validate, format_document

doc = load("/usr/share/applications/example.desktop")
issues = validate(doc)
if issues:
  for issue in issues:
    print(issue.code, issue.message)

print(format_document(doc))
```

## References and specifications

### XDG Desktop Entry Specification

- [XDG Desktop Entry Specification (latest)](https://xdg.pages.freedesktop.org/xdg-specs/desktop-entry/latest)
  - [From Free Desktop](https://specifications.freedesktop.org/desktop-entry/latest/)
  - [Single pages](https://xdg.pages.freedesktop.org/xdg-specs/desktop-entry/latest-single)

### Free Desktop

- [PyXDG](https://www.freedesktop.org/wiki/Software/pyxdg/)
  - [GitLab](https://gitlab.freedesktop.org/xdg/pyxdg)
  - [Read the Docs](https://pyxdg.readthedocs.io/en/latest/)
