from __future__ import annotations

import os
from typing import Any

from .stylesheet_imports import (
    expand_css_imports as _expand_css_imports,
    expand_less_imports as _expand_less_imports,
)
from .stylesheet_less import (
    _apply_tone,
    _clamp_channel,
    _combine_selectors,
    _find_closing_paren,
    _format_hex,
    _parse_color,
    _parse_percent,
    _split_call_args,
    _split_selectors,
    _strip_less_comments,
    compile_less_minimal,
    resolve_color_functions as _resolve_color_functions,
)


def load_stylesheet_from_paths(
    less_path: str,
    css_path: str,
    logger: Any = None,
    debug: bool = False,
) -> str:
    """
    Load desktop stylesheet with minimal LESS support.
    Priority:
    1) .less source (compiled at runtime)
    2) .css fallback
    """
    if os.path.exists(less_path):
        try:
            with open(less_path, "r", encoding="utf-8") as f:
                less_source = f.read()
            less_source = _expand_less_imports(
                less_source,
                os.path.dirname(os.path.abspath(less_path)),
                {os.path.abspath(less_path)},
            )
            return compile_less_minimal(less_source)
        except Exception as e:
            if logger:
                logger.warning(
                    f"Failed to compile LESS stylesheet ({less_path}): {e}",
                    "desktop",
                )
            elif debug:
                print(f"Failed to compile LESS stylesheet ({less_path}): {e}")

    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            css_source = f.read()
        return _expand_css_imports(
            css_source,
            os.path.dirname(os.path.abspath(css_path)),
            {os.path.abspath(css_path)},
        )

    return ""


__all__ = [
    "compile_less_minimal",
    "load_stylesheet_from_paths",
    "_apply_tone",
    "_clamp_channel",
    "_combine_selectors",
    "_expand_less_imports",
    "_expand_css_imports",
    "_find_closing_paren",
    "_format_hex",
    "_parse_color",
    "_parse_percent",
    "_split_call_args",
    "_split_selectors",
    "_strip_less_comments",
    "_resolve_color_functions",
]
