from __future__ import annotations

import re
from typing import Any


def _clamp_channel(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _parse_percent(value: str) -> float:
    raw = value.strip()
    if raw.endswith("%"):
        raw = raw[:-1].strip()
    return max(0.0, min(100.0, float(raw))) / 100.0


def _parse_color(value: str) -> tuple[int, int, int] | None:
    text = value.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", text):
        return tuple(int(c * 2, 16) for c in text[1:4])  # type: ignore[return-value]
    if re.fullmatch(r"#[0-9a-f]{6}", text):
        return (
            int(text[1:3], 16),
            int(text[3:5], 16),
            int(text[5:7], 16),
        )
    rgb_match = re.fullmatch(
        r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", text
    )
    if rgb_match:
        channels = tuple(max(0, min(255, int(part))) for part in rgb_match.groups())
        return channels  # type: ignore[return-value]
    return None


def _format_hex(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def _find_closing_paren(text: str, open_idx: int) -> int:
    depth = 0
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return idx
    return -1


def _split_call_args(args: str) -> list[str]:
    out: list[str] = []
    current = ""
    depth = 0
    for ch in args:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            out.append(current.strip())
            current = ""
            continue
        current += ch
    if current.strip():
        out.append(current.strip())
    return out


def _apply_tone(
    color: tuple[int, int, int], fn_name: str, amount: float
) -> tuple[int, int, int]:
    if fn_name in ("lighter", "lighten"):
        return tuple(
            _clamp_channel(channel + (255 - channel) * amount) for channel in color
        )  # type: ignore[return-value]
    return tuple(_clamp_channel(channel * (1.0 - amount)) for channel in color)  # type: ignore[return-value]


def resolve_color_functions(text: str) -> str:
    pattern = re.compile(r"\b(lighter|lighten|darker|darken)\s*\(", flags=re.I)
    out = text
    for _ in range(20):
        match = pattern.search(out)
        if not match:
            break
        fn_name = match.group(1).lower()
        open_idx = out.find("(", match.start())
        close_idx = _find_closing_paren(out, open_idx)
        if close_idx == -1:
            break

        args = _split_call_args(out[open_idx + 1 : close_idx])
        if len(args) != 2:
            break

        color_value = resolve_color_functions(args[0])
        amount_value = args[1]
        replacement = out[match.start() : close_idx + 1]
        try:
            parsed_color = _parse_color(color_value)
            if parsed_color is None:
                break
            amount = _parse_percent(amount_value)
            replacement = _format_hex(_apply_tone(parsed_color, fn_name, amount))
        except Exception:
            break

        out = out[: match.start()] + replacement + out[close_idx + 1 :]
    return out


def _strip_less_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"//[^\n]*", "", source)
    return source


def _split_selectors(selector_text: str) -> list[str]:
    return [s.strip() for s in selector_text.split(",") if s.strip()]


def _combine_selectors(parents: list[str], children: list[str]) -> list[str]:
    combined: list[str] = []
    for parent in parents:
        for child in children:
            if "&" in child:
                combined.append(child.replace("&", parent).strip() if parent else child.replace("&", "").strip())
            elif parent:
                combined.append(f"{parent} {child}")
            else:
                combined.append(child)
    return combined


def compile_less_minimal(source: str) -> str:
    source = _strip_less_comments(source)

    var_pattern = re.compile(r"@([a-zA-Z_][\w-]*)\s*:\s*([^;{}]+);")
    variables: dict[str, str] = {name: value.strip() for name, value in var_pattern.findall(source)}
    source = var_pattern.sub("", source)
    resolved_variables: dict[str, str] = {}

    def resolve_variable(name: str, stack: set[str] | None = None) -> str:
        if name in resolved_variables:
            return resolved_variables[name]
        if name not in variables:
            return f"@{name}"
        stack = stack or set()
        if name in stack:
            return variables[name]
        stack.add(name)
        raw_value = variables[name]

        def replace_in_value(match: re.Match[str]) -> str:
            inner_name = match.group(1)
            if inner_name == name:
                return match.group(0)
            return resolve_variable(inner_name, stack)

        expanded = re.sub(r"@([a-zA-Z_][\w-]*)", replace_in_value, raw_value)
        expanded = resolve_color_functions(expanded)
        stack.remove(name)
        resolved_variables[name] = expanded
        return expanded

    for variable_name in list(variables.keys()):
        resolve_variable(variable_name)

    def replace_var(match: re.Match[str]) -> str:
        name = match.group(1)
        return resolved_variables.get(name, variables.get(name, match.group(0)))

    source = re.sub(r"@([a-zA-Z_][\w-]*)", replace_var, source)
    source = resolve_color_functions(source)

    out_rules: list[str] = []
    stack: list[dict[str, Any]] = [{"selectors": [""], "decls": []}]
    token = ""
    in_string = False
    string_char = ""

    def flush_declaration(text: str) -> None:
        decl = text.strip()
        if decl and ":" in decl:
            stack[-1]["decls"].append(decl)

    def flush_selector(text: str) -> None:
        selector_text = text.strip()
        if not selector_text:
            return
        selectors = _combine_selectors(stack[-1]["selectors"], _split_selectors(selector_text))
        stack.append({"selectors": selectors, "decls": []})

    def close_block() -> None:
        if len(stack) <= 1:
            return
        block = stack.pop()
        if not block["decls"]:
            return
        body = ";\n  ".join(block["decls"]) + ";"
        for selector in block["selectors"]:
            if selector:
                out_rules.append(f"{selector} {{\n  {body}\n}}")

    for ch in source:
        if in_string:
            token += ch
            if ch == string_char:
                in_string = False
            continue
        if ch in ("'", '"'):
            in_string = True
            string_char = ch
            token += ch
            continue
        if ch == "{":
            flush_selector(token)
            token = ""
            continue
        if ch == ";":
            flush_declaration(token)
            token = ""
            continue
        if ch == "}":
            flush_declaration(token)
            token = ""
            close_block()
            continue
        token += ch

    return "\n\n".join(out_rules).strip()
