"""
JSONPath accessor using jsonpath-ng library.
Supports robust querying (filters, slices) via jsonpath-ng.
Fallbacks to custom logic for creation/setting if path doesn't exist.
"""

from jsonpath_ng import parse
from jsonpath_ng.ext import parse as parse_ext
from ..logging import get_logger
import re

# Regex for simple dot/index notation used in creation fallback
SEGMENT_RE = re.compile(r"\.?([a-zA-Z0-9_]+)|\[(\d+)\]")


def get_value(data, path: str, default=None):
    """Retrieves a value from nested data using jsonpath-ng."""
    if not path or data is None:
        return default

    try:
        # Try extended syntax first
        jsonpath_expr = parse_ext(path)
        matches = jsonpath_expr.find(data)

        if not matches:
            return default

        # Return first match value
        return matches[0].value
    except Exception:
        # Fallback or return default on syntax error
        return default


def _parse_path_segments(path: str):
    """Parses a path string into a list of keys (str) or indices (int)."""
    segments = []
    for match in SEGMENT_RE.finditer(path):
        key, index = match.groups()
        if key is not None:
            segments.append(key)
        elif index is not None:
            segments.append(int(index))
    return segments


def set_value(data, path: str, value):
    """
    Sets a value in nested data.
    Attempts to use jsonpath-ng for update.
    If path doesn't exist, falls back to custom creation logic.
    """
    if not path:
        return value

    try:
        # Try to update existing path using jsonpath-ng
        jsonpath_expr = parse_ext(path)
        # Check if path exists
        matches = jsonpath_expr.find(data)
        if matches:
            jsonpath_expr.update(data, value)
            return data
    except Exception:
        get_logger().debug("ERROR JSON PATH desktop/utils/jsonpath@set_value")

    # Fallback: Create structure (Custom Logic)
    # This only works for simple dot/index notation, not complex filters
    segments = _parse_path_segments(path)
    if not segments:
        return data

    if data is None:
        data = [] if isinstance(segments[0], int) else {}

    current = data
    for i, seg in enumerate(segments[:-1]):
        next_seg = segments[i + 1]
        next_is_list = isinstance(next_seg, int)

        if isinstance(seg, int):
            # List behavior
            while len(current) <= seg:
                current.append(None)
            if current[seg] is None:
                current[seg] = [] if next_is_list else {}
            current = current[seg]
        else:
            # Dict behavior
            if seg not in current or current[seg] is None:
                current[seg] = [] if next_is_list else {}
            current = current[seg]

    # Set leaf
    last = segments[-1]
    if isinstance(last, int):
        if isinstance(current, list):
            while len(current) <= last:
                current.append(None)
            current[last] = value
    else:
        if isinstance(current, dict):
            current[last] = value

    return data
