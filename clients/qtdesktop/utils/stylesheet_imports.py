from __future__ import annotations

import os
import re


_LESS_IMPORT_PATTERN = re.compile(
    r'^\s*@import\s+(?:\(\s*less\s*\)\s*)?["\']([^"\']+)["\']\s*;\s*$',
    flags=re.M,
)
_CSS_IMPORT_PATTERN = re.compile(
    r'^\s*@import\s+url\(\s*["\']?([^"\')]+)["\']?\s*\)\s*;\s*$',
    flags=re.M,
)


def _expand_imports(source: str, base_dir: str, seen: set[str], pattern: re.Pattern[str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        rel_path = match.group(1).strip()
        target_path = os.path.abspath(os.path.normpath(os.path.join(base_dir, rel_path)))
        if target_path in seen or not os.path.exists(target_path):
            return ""
        seen.add(target_path)
        with open(target_path, "r", encoding="utf-8") as imported:
            imported_source = imported.read()
        return _expand_imports(imported_source, os.path.dirname(target_path), seen, pattern)

    return pattern.sub(_replace, source)


def expand_less_imports(source: str, base_dir: str, seen: set[str]) -> str:
    return _expand_imports(source, base_dir, seen, _LESS_IMPORT_PATTERN)


def expand_css_imports(source: str, base_dir: str, seen: set[str]) -> str:
    return _expand_imports(source, base_dir, seen, _CSS_IMPORT_PATTERN)
