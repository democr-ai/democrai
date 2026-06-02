from __future__ import annotations


# Source of truth: Qt 6 Style Sheets Reference, "List of Properties".
# https://doc.qt.io/qt-6/stylesheet-reference.html#list-of-properties
QSS_ALLOWED_PROPERTIES = frozenset(
    {
        "-qt-background-role",
        "-qt-style-features",
        "accent-color",
        "alternate-background-color",
        "background",
        "background-attachment",
        "background-clip",
        "background-color",
        "background-image",
        "background-origin",
        "background-position",
        "background-repeat",
        "border",
        "border-bottom",
        "border-bottom-color",
        "border-bottom-left-radius",
        "border-bottom-right-radius",
        "border-bottom-style",
        "border-bottom-width",
        "border-color",
        "border-image",
        "border-left",
        "border-left-color",
        "border-left-style",
        "border-left-width",
        "border-radius",
        "border-right",
        "border-right-color",
        "border-right-style",
        "border-right-width",
        "border-style",
        "border-top",
        "border-top-color",
        "border-top-left-radius",
        "border-top-right-radius",
        "border-top-style",
        "border-top-width",
        "border-width",
        "bottom",
        "button-layout",
        "color",
        "dialogbuttonbox-buttons-have-icons",
        "font",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "gridline-color",
        "height",
        "icon",
        "icon-size",
        "image",
        "image-position",
        "left",
        "letter-spacing",
        "lineedit-password-character",
        "lineedit-password-mask-delay",
        "margin",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "margin-top",
        "max-height",
        "max-width",
        "messagebox-text-interaction-flags",
        "min-height",
        "min-width",
        "opacity",
        "outline",
        "outline-bottom-left-radius",
        "outline-bottom-right-radius",
        "outline-color",
        "outline-offset",
        "outline-radius",
        "outline-style",
        "outline-top-left-radius",
        "outline-top-right-radius",
        "outline-width",
        "padding",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "padding-top",
        "paint-alternating-row-colors-for-empty-area",
        "placeholder-text-color",
        "position",
        "right",
        "selection-background-color",
        "selection-color",
        "show-decoration-selected",
        "spacing",
        "subcontrol-origin",
        "subcontrol-position",
        "text-align",
        "text-decoration",
        "titlebar-show-maximize-button",
        "titlebar-show-minimize-button",
        "top",
        "widget-animation-duration",
        "width",
        "word-spacing",
    }
)


def _split_declarations(style: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote = ""
    for index, char in enumerate(style):
        if quote:
            if char == quote and (index == 0 or style[index - 1] != "\\"):
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            depth += 1
            continue
        if char == ")" and depth:
            depth -= 1
            continue
        if char == ";" and depth == 0:
            parts.append(style[start:index])
            start = index + 1
    tail = style[start:]
    if tail.strip():
        parts.append(tail)
    return parts


def _sanitize_declaration_block(block: str) -> str:
    kept: list[str] = []
    for declaration in _split_declarations(block):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        raw_prop = name.strip()
        prop = raw_prop.lower()
        if prop not in QSS_ALLOWED_PROPERTIES and not prop.startswith("qproperty-"):
            continue
        value = value.strip()
        if not value:
            continue
        kept.append(f"{raw_prop if prop.startswith('qproperty-') else prop}: {value};")
    return " ".join(kept)


def sanitize_qss_style(style: object) -> str:
    """Drop non-QSS declarations from a style payload before Qt sees it."""
    text = str(style or "").strip()
    if not text:
        return ""
    if "{" not in text or "}" not in text:
        return _sanitize_declaration_block(text)

    out: list[str] = []
    cursor = 0
    while True:
        open_pos = text.find("{", cursor)
        if open_pos < 0:
            break
        close_pos = text.find("}", open_pos + 1)
        if close_pos < 0:
            break
        selector = text[cursor:open_pos].strip()
        body = _sanitize_declaration_block(text[open_pos + 1 : close_pos])
        if selector and body:
            out.append(f"{selector} {{ {body} }}")
        cursor = close_pos + 1
    return "\n".join(out)


def qss_for_widget_style(style: object, comp_id: str | None = None) -> str:
    """Return sanitized QSS, scoping declaration-only styles to a widget id."""
    sanitized = sanitize_qss_style(style)
    if not sanitized:
        return ""
    if "{" in sanitized or "}" in sanitized:
        return sanitized
    safe_id = str(comp_id or "").strip()
    if safe_id and safe_id != "unknown":
        return f"#{safe_id} {{ {sanitized} }}"
    return sanitized
