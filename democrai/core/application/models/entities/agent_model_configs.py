from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import AgentModelConfig, ModelRegistry
from democrai.core.platform.utils.identity import to_optional_int


_POLICIES = {"by_system", "by_parent", "specific_model"}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [value] if value else []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


class AgentModelConfigsCoreModel(BaseCoreModel):
    name = "agent_model_configs"
    sqlalchemy_model = AgentModelConfig

    def serialize_row(self, item: AgentModelConfig) -> dict[str, Any]:
        return {
            "id": item.id,
            "agent_name": item.agent_name,
            "model_policy": item.model_policy,
            "model_registry_id": item.model_registry_id,
            "extra_tools": _strings(item.extra_tools),
            "extra_skills": _strings(item.extra_skills),
            "extra_mcp_servers": _strings(item.extra_mcp_servers),
            "extra_agents": _strings(item.extra_agents),
            "max_iterations": item.max_iterations,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [{"field": "agent_name", "type": "text"}]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "agent_name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "model_policy", "type": "str", "filterable": False},
            {"field": "model_registry_id", "type": "int", "filterable": False},
            {"field": "max_iterations", "type": "int", "filterable": False},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        agent_name = str(filters.get("agent_name") or "").strip()
        if agent_name:
            query = query.filter(AgentModelConfig.agent_name.ilike(f"%{agent_name}%"))
        return query

    def get_info(self, agent_name: str) -> dict[str, Any] | None:
        if not agent_name:
            return None
        with SessionLocal() as session:
            row = session.query(AgentModelConfig).filter(AgentModelConfig.agent_name == agent_name).first()
            return self.serialize_detail(row) if row is not None else None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_name = str(payload.get("agent_name") or "").strip()
        if not agent_name:
            raise ValueError("agent_name_required")
        with SessionLocal() as session:
            existing = session.query(AgentModelConfig).filter(AgentModelConfig.agent_name == agent_name).first()
            if existing is not None:
                return self._apply_payload(session, existing, payload)
            row = AgentModelConfig(agent_name=agent_name)
            session.add(row)
            return self._apply_payload(session, row, payload)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = session.query(AgentModelConfig).filter(AgentModelConfig.id == entity_id).first()
            if row is None:
                return None
            return self._apply_payload(session, row, payload)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = session.query(AgentModelConfig).filter(AgentModelConfig.id == entity_id).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def _apply_payload(self, session, row: AgentModelConfig, payload: dict[str, Any]) -> dict[str, Any]:
        policy = str(payload.get("model_policy") or "by_system").strip()
        if policy not in _POLICIES:
            raise ValueError("invalid_model_policy")
        model_registry_id = to_optional_int(payload.get("model_registry_id"))
        if policy == "specific_model" and model_registry_id is not None:
            exists = session.query(ModelRegistry.id).filter(ModelRegistry.id == model_registry_id).first()
            if exists is None:
                raise ValueError("model_not_found")
        row.model_policy = policy
        row.model_registry_id = model_registry_id if policy == "specific_model" else None
        row.extra_tools = _strings(payload.get("extra_tools"))
        row.extra_skills = _strings(payload.get("extra_skills"))
        row.extra_mcp_servers = _strings(payload.get("extra_mcp_servers"))
        row.extra_agents = _strings(payload.get("extra_agents"))
        raw_max_iterations = payload.get("max_iterations")
        max_iterations = (
            int(raw_max_iterations)
            if raw_max_iterations not in (None, "")
            else None
        )
        row.max_iterations = (
            max_iterations
            if max_iterations is not None and max_iterations > 0
            else None
        )
        session.commit()
        session.refresh(row)
        return self.serialize_detail(row)
