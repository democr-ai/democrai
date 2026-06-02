from typing import Any, List, Sequence
from democrai.core.runtime.foundation.app import app_ctx
from .base import (
    VectorProvider,
    ProviderInfo,
    IndexSpec,
    UserScope,
    VectorDoc,
    Query,
    Match,
    VectorStoreError,
)
from enum import Enum


class ReadPolicy(str, Enum):
    STRICT_PRIMARY = "strict_primary"
    PREFER_PRIMARY = "prefer_primary"
    PREFER_SECONDARY = "prefer_secondary"
    STRICT_SECONDARY = "strict_secondary"


class WritePolicy(str, Enum):
    PRIMARY_ONLY = "primary_only"
    DUAL_WRITE = "dual_write"
    SECONDARY_ONLY = "secondary_only"


def _debug_exception(message: str) -> None:
    logger = app_ctx().logger
    try:
        logger.debug(message, exc_info=True)
    except TypeError:
        logger.debug(message)


class CompositeVectorStore(VectorProvider):
    def __init__(
        self,
        primary: VectorProvider,
        secondary: VectorProvider,
        write_policy: WritePolicy = WritePolicy.DUAL_WRITE,
        read_policy: ReadPolicy = ReadPolicy.PREFER_PRIMARY,
    ):
        self.primary = primary
        self.secondary = secondary
        self.write_policy = write_policy
        self.read_policy = read_policy

    async def info(self) -> ProviderInfo:
        if self.read_policy in (ReadPolicy.STRICT_SECONDARY, ReadPolicy.PREFER_SECONDARY):
            return await self.secondary.info()
        return await self.primary.info()

    async def ensure_index(self, spec: IndexSpec) -> None:
        if self.write_policy == WritePolicy.PRIMARY_ONLY:
            await self.primary.ensure_index(spec)
        elif self.write_policy == WritePolicy.SECONDARY_ONLY:
            await self.secondary.ensure_index(spec)
        else:
            await self.primary.ensure_index(spec)
            await self.secondary.ensure_index(spec)

    async def drop_index(self, spec: IndexSpec) -> None:
        if self.write_policy == WritePolicy.PRIMARY_ONLY:
            await self.primary.drop_index(spec)
        elif self.write_policy == WritePolicy.SECONDARY_ONLY:
            await self.secondary.drop_index(spec)
        else:
            await self.primary.drop_index(spec)
            await self.secondary.drop_index(spec)

    async def upsert(
        self, scope: UserScope, spec: IndexSpec, docs: Sequence[VectorDoc]
    ) -> None:
        if self.write_policy == WritePolicy.PRIMARY_ONLY:
            await self.primary.upsert(scope, spec, docs)
        elif self.write_policy == WritePolicy.SECONDARY_ONLY:
            await self.secondary.upsert(scope, spec, docs)
        else:  # DUAL_WRITE
            exceptions = []
            try:
                await self.primary.upsert(scope, spec, docs)
            except Exception as exc:
                exceptions.append(f"Primary failed: {exc}")

            try:
                await self.secondary.upsert(scope, spec, docs)
            except Exception as exc:
                exceptions.append(f"Secondary failed: {exc}")

            if exceptions:
                raise VectorStoreError(
                    f"Dual-write upsert failed: {'; '.join(exceptions)}"
                )

    async def delete_ids(
        self, scope: UserScope, spec: IndexSpec, ids: Sequence[str]
    ) -> int:
        if self.write_policy == WritePolicy.PRIMARY_ONLY:
            return await self.primary.delete_ids(scope, spec, ids)
        if self.write_policy == WritePolicy.SECONDARY_ONLY:
            return await self.secondary.delete_ids(scope, spec, ids)
        count = 0
        exceptions = []
        try:
            count = await self.primary.delete_ids(scope, spec, ids)
        except Exception as exc:
            _debug_exception(
                "ERROR DELETE IDS primary core/infrastructure/storage/vector/composite@delete_ids"
            )
            exceptions.append(f"Primary failed: {exc}")
        try:
            await self.secondary.delete_ids(scope, spec, ids)
        except Exception as exc:
            _debug_exception(
                "ERROR DELETE IDS secondary core/infrastructure/storage/vector/composite@delete_ids"
            )
            exceptions.append(f"Secondary failed: {exc}")
        if exceptions:
            raise VectorStoreError(
                f"Dual-write delete_ids failed: {'; '.join(exceptions)}"
            )
        return count

    async def delete_by_filter(
        self, scope: UserScope, spec: IndexSpec, flt: Any
    ) -> int:
        if self.write_policy == WritePolicy.PRIMARY_ONLY:
            return await self.primary.delete_by_filter(scope, spec, flt)
        if self.write_policy == WritePolicy.SECONDARY_ONLY:
            return await self.secondary.delete_by_filter(scope, spec, flt)
        count = 0
        exceptions = []
        try:
            count = await self.primary.delete_by_filter(scope, spec, flt)
        except Exception as exc:
            _debug_exception(
                "ERROR DELETE BY FILTER primary core/infrastructure/storage/vector/composite@delete_by_filter"
            )
            exceptions.append(f"Primary failed: {exc}")
        try:
            await self.secondary.delete_by_filter(scope, spec, flt)
        except Exception as exc:
            _debug_exception(
                "ERROR DELETE BY FILTER secondary core/infrastructure/storage/vector/composite@delete_by_filter"
            )
            exceptions.append(f"Secondary failed: {exc}")
        if exceptions:
            raise VectorStoreError(
                f"Dual-write delete_by_filter failed: {'; '.join(exceptions)}"
            )
        return count

    async def query(self, scope: UserScope, spec: IndexSpec, q: Query) -> List[Match]:
        if self.read_policy in (ReadPolicy.STRICT_PRIMARY, ReadPolicy.PREFER_PRIMARY):
            try:
                return await self.primary.query(scope, spec, q)
            except Exception:
                if self.read_policy == ReadPolicy.STRICT_PRIMARY:
                    raise
                return await self.secondary.query(scope, spec, q)
        else:  # PREFER_SECONDARY or STRICT_SECONDARY
            try:
                return await self.secondary.query(scope, spec, q)
            except Exception:
                if self.read_policy == ReadPolicy.STRICT_SECONDARY:
                    raise
                return await self.primary.query(scope, spec, q)

    async def rebuild(self, spec: IndexSpec) -> None:
        if self.write_policy == WritePolicy.PRIMARY_ONLY:
            await self.primary.rebuild(spec)
        elif self.write_policy == WritePolicy.SECONDARY_ONLY:
            await self.secondary.rebuild(spec)
        else:
            await self.primary.rebuild(spec)
            await self.secondary.rebuild(spec)
