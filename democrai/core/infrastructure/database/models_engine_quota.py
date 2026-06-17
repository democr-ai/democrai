from __future__ import annotations

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import UniqueConstraint

from democrai.core.infrastructure.database.models import Base
from democrai.core.platform.utils.timezone import utc_now_naive


class EngineQuotaCounter(Base):
    __tablename__ = "engine_quota_counters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True)
    period_count = Column(Integer, nullable=False, default=1)
    period_unit = Column(String(16), nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<EngineQuotaCounter(name='{self.name}', "
            f"period='{self.period_count} {self.period_unit}')>"
        )


class EngineQuotaLimit(Base):
    __tablename__ = "engine_quota_limits"
    __table_args__ = (
        UniqueConstraint(
            "counter_id",
            "engine_row_id",
            "scope_type",
            "scope_id",
            "metric_type",
            name="uq_engine_quota_limit_scope",
        ),
        Index(
            "ix_engine_quota_limits_engine_scope",
            "engine_row_id",
            "scope_type",
            "scope_id",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    counter_id = Column(
        Integer,
        ForeignKey("engine_quota_counters.id"),
        nullable=False,
        index=True,
    )
    engine_row_id = Column(
        Integer,
        ForeignKey("engine_registry.id"),
        nullable=False,
        index=True,
    )
    scope_type = Column(String(32), nullable=False, index=True)
    scope_id = Column(Integer, nullable=True, index=True)
    metric_type = Column(String(32), nullable=False, index=True)
    limit_value = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return (
            f"<EngineQuotaLimit(engine_row_id={self.engine_row_id}, "
            f"scope='{self.scope_type}:{self.scope_id}')>"
        )
