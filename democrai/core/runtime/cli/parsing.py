from __future__ import annotations

from typing import Any


def coerce_cli_value(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_module_command_tokens(tokens: list[str]) -> tuple[list[Any], dict[str, Any]]:
    positional: list[Any] = []
    kwargs: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
            key = token[2:].replace("-", "_")
            if not key:
                raise ValueError("empty option name")
            if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
                kwargs[key] = coerce_cli_value(tokens[index + 1])
                index += 2
            else:
                kwargs[key] = True
                index += 1
            continue
        if "=" in token and not token.startswith("="):
            key, raw_value = token.split("=", 1)
            kwargs[key.replace("-", "_")] = coerce_cli_value(raw_value)
            index += 1
            continue
        positional.append(coerce_cli_value(token))
        index += 1
    return positional, kwargs
