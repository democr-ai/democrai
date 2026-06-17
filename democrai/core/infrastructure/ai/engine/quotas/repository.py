from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from democrai.core.application.ai.engine.quotas.types import METRIC_TOTAL_TOKENS
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models_engine_quota import EngineQuotaCounter
from democrai.core.infrastructure.database.models_engine_quota import EngineQuotaLimit
from democrai.core.runtime.foundation.app import app_ctx


@dataclass(frozen=True)
class EngineQuotaLimitRow:
    limit_id: int
    counter_id: int
    period_count: int
    period_unit: str
    engine_row_id: int
    scope_type: str
    scope_id: int | None
    metric_type: str
    limit_value: int


class EngineQuotaRepository:
    def limits_for_engine(self, *, engine_row_id: int) -> list[EngineQuotaLimitRow]:
        with SessionLocal() as session:
            rows = (
                session.query(EngineQuotaLimit, EngineQuotaCounter)
                .join(EngineQuotaCounter, EngineQuotaCounter.id == EngineQuotaLimit.counter_id)
                .filter(EngineQuotaLimit.engine_row_id == int(engine_row_id))
                .order_by(EngineQuotaCounter.id.asc(), EngineQuotaLimit.id.asc())
                .all()
            )
            return [
                EngineQuotaLimitRow(
                    limit_id=int(limit.id),
                    counter_id=int(counter.id),
                    period_count=int(counter.period_count),
                    period_unit=str(counter.period_unit),
                    engine_row_id=int(limit.engine_row_id),
                    scope_type=str(limit.scope_type),
                    scope_id=int(limit.scope_id) if limit.scope_id is not None else None,
                    metric_type=str(limit.metric_type),
                    limit_value=int(limit.limit_value),
                )
                for limit, counter in rows
            ]

    def aggregate_usage(
        self,
        *,
        metric_type: str,
        engine_row_id: int,
        started_at: datetime,
        ended_at: datetime,
        user_id: int | None = None,
        organization_id: int | None = None,
        session_id: str | None = None,
    ) -> int:
        store = getattr(app_ctx(), "obs_store", None)
        if store is None:
            raise RuntimeError("engine_quota_observability_store_unavailable")
        return int(
            store.aggregate_ai_model_usage(
                metric_type=str(metric_type),
                engine_row_id=int(engine_row_id),
                started_at=started_at,
                ended_at=ended_at,
                user_id=user_id,
                organization_id=organization_id,
                session_id=session_id,
            )
            or 0
        )

    def sum_usage_total_tokens(
        self,
        *,
        engine_row_id: int,
        started_at: datetime,
        ended_at: datetime,
        user_id: int | None = None,
        organization_id: int | None = None,
        session_id: str | None = None,
    ) -> int:
        return self.aggregate_usage(
            metric_type=METRIC_TOTAL_TOKENS,
            engine_row_id=engine_row_id,
            started_at=started_at,
            ended_at=ended_at,
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
        )
