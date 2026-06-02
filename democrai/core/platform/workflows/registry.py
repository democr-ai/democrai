from __future__ import annotations

from typing import Dict, Optional

from .models import WorkflowDefinition


class WorkflowRegistry:
    def __init__(self) -> None:
        self._workflows: Dict[str, WorkflowDefinition] = {}

    def register(self, definition: WorkflowDefinition) -> None:
        self._workflows[str(definition.id)] = definition

    def get(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        return self._workflows.get(workflow_id if isinstance(workflow_id, str) else "")

    def get_all(self, *, module_name: str | None = None) -> list[WorkflowDefinition]:
        values = list(self._workflows.values())
        if module_name is None:
            return values
        return [item for item in values if item.module_name == module_name]


workflow_registry = WorkflowRegistry()
