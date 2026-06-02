from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    LargeBinary,
    Index,
)
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass


class VectorIndex(Base):
    __tablename__ = "vector_indices"
    tenant_id = Column(String, primary_key=True)
    app_id = Column(String, primary_key=True)
    name = Column(String, primary_key=True)
    dim = Column(Integer, nullable=False)
    metric = Column(String, nullable=False)
    model_id = Column(String, nullable=True)
    model_version = Column(String, nullable=True)
    table_name = Column(String, nullable=False)


class VectorPayload(Base):
    __tablename__ = "vector_payloads"
    id = Column(String, primary_key=True)
    tenant_id = Column(String, primary_key=True)
    app_id = Column(String, primary_key=True)
    index_name = Column(String, primary_key=True)
    user_id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, primary_key=True, default=0)
    vector = Column(LargeBinary, nullable=False)
    metadata_json = Column("metadata", Text, nullable=False, default="{}")
    timestamp = Column(Integer, nullable=False)

    __table_args__ = (
        Index(
            "idx_vector_payloads_scope",
            "tenant_id",
            "app_id",
            "index_name",
            "user_id",
            "organization_id",
        ),
    )
