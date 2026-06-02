from __future__ import annotations

import os
import sys


def get_resource_path(relative_path: str) -> str:
    """
    Absolute path to packaged resources.
    - Dev:   relative to desktop package
    - Compiled runtime: relative to sys._MEIPASS when present
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS  # pylint: disable=no-member
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)
