from __future__ import annotations

import re


_BR_RE = re.compile(r"(?i)<br\s*/?>")
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")


def normalize_markdown_for_qt(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""

    # Normalize typographic unicode that often breaks Qt markdown layout.
    text = (
        text.replace("\u00a0", " ")  # no-break space
        .replace("\u202f", " ")  # narrow no-break space
        .replace("\u2011", "-")  # non-breaking hyphen
        .replace("\u2013", "-")  # en-dash
        .replace("\u2014", "-")  # em-dash
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )

    lines = text.splitlines()
    normalized: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if _TABLE_DIVIDER_RE.match(stripped):
                normalized.append(stripped)
                continue

            # Keep table rows plain and single-line for Qt markdown stability.
            row = _BR_RE.sub(" ; ", stripped)
            row = row.replace("•", "- ")
            # Collapse accidental excessive spaces in table cells.
            row = re.sub(r"\s{2,}", " ", row)
            normalized.append(row)
            continue

        normalized.append(_BR_RE.sub("\n", line))

    cleaned = "\n".join(normalized)
    # Keep vertical rhythm deterministic.
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned
