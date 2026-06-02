from __future__ import annotations
import hashlib
from dataclasses import dataclass
from enum import Enum, Flag, auto
from typing import Any, List, Mapping, Optional, Protocol, Sequence, Tuple, Union

# ---------------------------
# Core domain objects
# ---------------------------


class Metric(str, Enum):
    COSINE = "cosine"
    L2 = "l2"


class Consistency(str, Enum):
    """Best-effort semantics across providers."""

    SESSION = "session"
    EVENTUAL = "eventual"
    STRONG = "strong"


class Capability(Flag):
    # Filters
    FILTER_EQ = auto()
    FILTER_IN = auto()
    FILTER_RANGE = auto()
    FILTER_AND = auto()
    FILTER_OR = auto()

    # Ops / behavior
    UPSERT_IDEMPOTENT = auto()
    UPSERT_ATOMIC = auto()
    DELETE_BY_FILTER = auto()
    BULK_UPSERT = auto()

    # Advanced search
    RETURN_VECTORS = auto()
    HYBRID_SEARCH = auto()

    # Operational
    REBUILD_INDEX = auto()
    MIGRATION_DUAL_WRITE = auto()
    PARTITIONS = auto()
    TTL = auto()

    # Security / tenancy
    USER_SCOPED = auto()  # provider guarantees per-user isolation


@dataclass(frozen=True)
class UserScope:
    """
    Hard isolation boundary for all vector operations.
    """

    user_id: int
    organization_id: Optional[int] = None


@dataclass(frozen=True)
class IndexSpec:
    """
    Stable handle for a logical index across providers.
    """

    tenant_id: str
    app_id: str
    name: str
    dim: int
    metric: Metric = Metric.COSINE
    embedding_model_id: Optional[str] = None
    embedding_model_version: Optional[str] = None


def physical_index_name(spec: IndexSpec, index_prefix: str = "democrai") -> str:
    prefix = str(index_prefix or "").strip()
    logical_key = f"{prefix}\x1f{spec.tenant_id}\x1f{spec.app_id}\x1f{spec.name}"
    digest = hashlib.sha256(logical_key.encode("utf-8")).hexdigest()[:32]
    return f"vec{digest}"


@dataclass(frozen=True)
class VectorDoc:
    id: str
    vector: Sequence[float]
    metadata: Optional[Mapping[str, Any]] = None  # provider-safe JSON-like


@dataclass(frozen=True)
class Match:
    id: str
    score: float  # normalized: higher is better
    metadata: Optional[Mapping[str, Any]] = None
    vector: Optional[Sequence[float]] = None


# ---------------------------
# Filtering model (portable)
# ---------------------------


class Op(str, Enum):
    EQ = "eq"
    IN = "in"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


@dataclass(frozen=True)
class Predicate:
    key: str
    op: Op
    value: Any


@dataclass(frozen=True)
class Filter:
    """
    Portable minimal filter AST.
    """

    and_: Tuple[Union["Filter", Predicate], ...] = ()
    or_: Tuple[Union["Filter", Predicate], ...] = ()
    pred: Optional[Predicate] = None

    @staticmethod
    def p(key: str, op: Op, value: Any) -> "Filter":
        return Filter(pred=Predicate(key, op, value))

    @staticmethod
    def AND(*items: Union["Filter", Predicate]) -> "Filter":
        return Filter(and_=tuple(items))

    @staticmethod
    def OR(*items: Union["Filter", Predicate]) -> "Filter":
        return Filter(or_=tuple(items))


# ---------------------------
# Results / errors
# ---------------------------


class VectorStoreError(RuntimeError):
    pass


class CapabilityError(VectorStoreError):
    def __init__(self, missing: Capability, message: str = ""):
        super().__init__(message or f"Missing capability: {missing}")
        self.missing = missing


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    version: Optional[str]
    capabilities: Capability


@dataclass(frozen=True)
class Query:
    vector: Sequence[float]
    top_k: int = 10
    filter: Optional[Filter] = None
    include_metadata: bool = True
    include_vectors: bool = False
    consistency: Consistency = Consistency.SESSION


# ---------------------------
# Score normalization
# ---------------------------


def normalize_score(metric: Metric, raw: float) -> float:
    """
    Normalize different backends into a stable 'higher is better' score in [0, 1].
    """
    if metric == Metric.COSINE:
        return max(0.0, min(1.0, (raw + 1.0) / 2.0))
    if metric == Metric.L2:
        d = max(0.0, raw)
        return 1.0 / (1.0 + d)
    return raw


# ---------------------------
# Provider interface
# ---------------------------


class VectorProvider(Protocol):
    async def info(self) -> ProviderInfo: ...
    async def ensure_index(self, spec: IndexSpec) -> None: ...
    async def drop_index(self, spec: IndexSpec) -> None: ...
    async def upsert(
        self, scope: UserScope, spec: IndexSpec, docs: Sequence[VectorDoc]
    ) -> None: ...
    async def delete_ids(
        self, scope: UserScope, spec: IndexSpec, ids: Sequence[str]
    ) -> int: ...
    async def delete_by_filter(
        self, scope: UserScope, spec: IndexSpec, flt: Filter
    ) -> int: ...
    async def query(
        self, scope: UserScope, spec: IndexSpec, q: Query
    ) -> List[Match]: ...
    async def rebuild(self, spec: IndexSpec) -> None: ...
