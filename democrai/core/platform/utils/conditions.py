from typing import Any, Dict, Union


class Condition:
    """Helper to build A2UI evaluation conditions."""

    def __init__(self, left: Any, op: str, right: Any):
        self.left = left
        self.op = op
        self.right = right

    def to_dict(self) -> Dict[str, Any]:
        return {"left": self.left, "op": self.op, "right": self.right}

    @staticmethod
    def AND(*conditions: Union["Condition", Dict]) -> Dict[str, Any]:
        return {
            "operator": "AND",
            "conditions": [
                c.to_dict() if hasattr(c, "to_dict") else c for c in conditions
            ],
        }

    @staticmethod
    def OR(*conditions: Union["Condition", Dict]) -> Dict[str, Any]:
        return {
            "operator": "OR",
            "conditions": [
                c.to_dict() if hasattr(c, "to_dict") else c for c in conditions
            ],
        }

    @staticmethod
    def bound(path: str, *, scope: str = "auto", default: Any = None) -> Dict[str, Any]:
        """Helper for explicit store-backed condition bindings."""
        return {"type": "store", "path": path, "scope": scope, "default": default}
