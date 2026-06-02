from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from dataclasses import dataclass, field
import time


@dataclass
class KGNode:
    id: str
    type: str
    user_id: int
    organization_id: Optional[int] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    name: Optional[str] = None
    external_ref: Optional[str] = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    deleted_at: Optional[int] = None


@dataclass
class KGEdge:
    id: str
    src: str
    dst: str
    type: str
    user_id: int
    organization_id: Optional[int] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: Optional[float] = None
    confidence: Optional[float] = None
    evidence_id: Optional[str] = None
    source: Optional[str] = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    deleted_at: Optional[int] = None


@dataclass
class KGEvidence:
    id: str
    kind: str
    ref: str
    user_id: int
    organization_id: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=lambda: int(time.time()))


class KGStorageProvider(ABC):
    @abstractmethod
    async def add_node(self, node: KGNode) -> None:
        pass

    @abstractmethod
    async def get_node(
        self, user_id: int, node_id: str, organization_id: Optional[int] = None
    ) -> Optional[KGNode]:
        pass

    @abstractmethod
    async def update_node(
        self,
        user_id: int,
        node_id: str,
        properties: Dict[str, Any],
        organization_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        pass

    @abstractmethod
    async def delete_node(
        self,
        user_id: int,
        node_id: str,
        soft: bool = True,
        organization_id: Optional[int] = None,
    ) -> None:
        pass

    @abstractmethod
    async def add_edge(self, edge: KGEdge) -> None:
        pass

    @abstractmethod
    async def get_edge(
        self, user_id: int, edge_id: str, organization_id: Optional[int] = None
    ) -> Optional[KGEdge]:
        pass

    @abstractmethod
    async def update_edge(
        self,
        user_id: int,
        edge_id: str,
        properties: Dict[str, Any],
        organization_id: Optional[int] = None,
        **kwargs,
    ) -> None:
        pass

    @abstractmethod
    async def delete_edge(
        self,
        user_id: int,
        edge_id: str,
        soft: bool = True,
        organization_id: Optional[int] = None,
    ) -> None:
        pass

    @abstractmethod
    async def add_evidence(self, evidence: KGEvidence) -> None:
        pass

    @abstractmethod
    async def delete_evidence(
        self,
        user_id: int,
        evidence_id: str,
        organization_id: Optional[int] = None,
    ) -> None:
        pass

    @abstractmethod
    async def link_edge_to_evidence(
        self,
        user_id: int,
        edge_id: str,
        evidence_id: str,
        organization_id: Optional[int] = None,
    ) -> None:
        pass

    @abstractmethod
    async def get_neighbors(
        self,
        user_id: int,
        node_id: str,
        edge_type: Optional[str] = None,
        limit: int = 10,
        organization_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns 1-hop neighbors with edge information."""
        pass

    @abstractmethod
    async def traversal(
        self,
        user_id: int,
        start_node_id: str,
        max_depth: int = 2,
        organization_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Performs a bounded traversal starting from a node."""
        pass

    @abstractmethod
    async def prune_orphan_nodes(
        self,
        user_id: int,
        node_ids: list[str],
        organization_id: Optional[int] = None,
    ) -> int:
        pass

    @abstractmethod
    def run_migrations(self) -> None:
        """Runs migrations for this domain."""
        pass
