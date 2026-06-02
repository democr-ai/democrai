from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.orm import declarative_base
from democrai.core.platform.utils.timezone import utc_now_naive


class UserMixin:
    """
    Mixin to automatically add user_id for multi-tenancy/isolation.
    """

    user_id = Column(Integer, index=True, nullable=False)
    organization_id = Column(Integer, index=True, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


Base = declarative_base()


def module_table_name(module_name: str, table_name: str) -> str:
    """Utility to generate consistent module table names."""
    return f"p_{module_name}_{table_name}"
