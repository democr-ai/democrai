from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, TYPE_CHECKING

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError

from democrai.core.infrastructure.database.models import ModuleCommandState
from democrai.core.platform.utils.timezone import format_app_datetime
from democrai.core.platform.utils.timezone import serialize_app_datetime
from democrai.core.platform.utils.timezone import utc_now_naive

if TYPE_CHECKING:
    from democrai.core.runtime.foundation.registry_types import ModuleCommandRegistration


@dataclass(frozen=True)
class ModuleCommandStateSnapshot:
    module_name: str
    command_name: str
    lifecycle: str
    status: str
    run_count: int
    last_started_at: datetime | None
    last_finished_at: datetime | None
    next_run_at: datetime | None
    last_error: str | None
    lease_owner: str | None
    lease_expires_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None

    def to_dict(self) -> dict:
        def _serialize(value: datetime | None) -> str | None:
            return serialize_app_datetime(value) if value is not None else None

        def _format(value: datetime | None) -> str | None:
            return format_app_datetime(value) if value is not None else None

        return {
            "module_name": self.module_name,
            "command_name": self.command_name,
            "lifecycle": self.lifecycle,
            "status": self.status,
            "run_count": self.run_count,
            "last_started_at": _serialize(self.last_started_at),
            "last_started_at_label": _format(self.last_started_at),
            "last_finished_at": _serialize(self.last_finished_at),
            "last_finished_at_label": _format(self.last_finished_at),
            "next_run_at": _serialize(self.next_run_at),
            "next_run_at_label": _format(self.next_run_at),
            "last_error": self.last_error,
            "lease_owner": self.lease_owner,
            "lease_expires_at": _serialize(self.lease_expires_at),
            "lease_expires_at_label": _format(self.lease_expires_at),
            "created_at": _serialize(self.created_at),
            "updated_at": _serialize(self.updated_at),
        }


class ModuleCommandStateStore:
    """Persistent store for module command runtime state and leases."""

    def _session(self):
        from democrai.core.runtime.foundation.app import app_ctx

        provider = app_ctx().db
        if provider is None:
            raise RuntimeError("Database provider is not initialized")
        return provider.get_session()

    def _to_snapshot(self, row: ModuleCommandState) -> ModuleCommandStateSnapshot:
        return ModuleCommandStateSnapshot(
            module_name=row.module_name,
            command_name=row.command_name,
            lifecycle=row.lifecycle,
            status=row.status,
            run_count=row.run_count,
            last_started_at=row.last_started_at,
            last_finished_at=row.last_finished_at,
            next_run_at=row.next_run_at,
            last_error=row.last_error,
            lease_owner=row.lease_owner,
            lease_expires_at=row.lease_expires_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def ensure_registered(self, definition: ModuleCommandRegistration) -> ModuleCommandStateSnapshot:
        session = self._session()
        now = utc_now_naive()
        try:
            row = (
                session.query(ModuleCommandState)
                .filter_by(command_name=definition.name)
                .one_or_none()
            )
            if row is None:
                row = ModuleCommandState(
                    module_name=definition.module_name,
                    command_name=definition.name,
                    lifecycle=definition.lifecycle,
                    status="idle",
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.module_name = definition.module_name
                row.lifecycle = definition.lifecycle
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return self._to_snapshot(row)
        except IntegrityError:
            session.rollback()
            row = (
                session.query(ModuleCommandState)
                .filter_by(command_name=definition.name)
                .one()
            )
            return self._to_snapshot(row)
        finally:
            session.close()

    def get(self, command_name: str) -> Optional[ModuleCommandStateSnapshot]:
        session = self._session()
        try:
            row = (
                session.query(ModuleCommandState)
                .filter_by(command_name=command_name)
                .one_or_none()
            )
            return self._to_snapshot(row) if row is not None else None
        finally:
            session.close()

    def list_states(self, *, module_name: str | None = None) -> list[ModuleCommandStateSnapshot]:
        session = self._session()
        try:
            query = session.query(ModuleCommandState)
            if module_name:
                query = query.filter_by(module_name=module_name)
            rows = query.order_by(
                ModuleCommandState.module_name.asc(),
                ModuleCommandState.command_name.asc(),
            ).all()
            return [self._to_snapshot(row) for row in rows]
        finally:
            session.close()

    def set_next_run(self, command_name: str, next_run_at: datetime | None) -> None:
        session = self._session()
        now = utc_now_naive()
        try:
            session.execute(
                update(ModuleCommandState)
                .where(ModuleCommandState.command_name == command_name)
                .values(next_run_at=next_run_at, updated_at=now)
            )
            session.commit()
        finally:
            session.close()

    def mark_started(self, definition: ModuleCommandRegistration, *, owner: str) -> None:
        self.ensure_registered(definition)
        session = self._session()
        now = utc_now_naive()
        try:
            session.execute(
                update(ModuleCommandState)
                .where(ModuleCommandState.command_name == definition.name)
                .values(
                    status="running",
                    run_count=ModuleCommandState.run_count + 1,
                    last_started_at=now,
                    updated_at=now,
                    last_error=None,
                    lease_owner=owner,
                    lease_expires_at=None,
                )
            )
            session.commit()
        finally:
            session.close()

    def try_acquire_lease(
        self,
        definition: ModuleCommandRegistration,
        *,
        owner: str,
        lease_ttl_seconds: float,
        increment_run_count: bool,
    ) -> bool:
        self.ensure_registered(definition)
        session = self._session()
        now = utc_now_naive()
        lease_expires_at = now + timedelta(seconds=max(1.0, lease_ttl_seconds))
        try:
            values = {
                "status": "running",
                "lease_owner": owner,
                "lease_expires_at": lease_expires_at,
                "last_started_at": now,
                "updated_at": now,
                "last_error": None,
            }
            if increment_run_count:
                values["run_count"] = ModuleCommandState.run_count + 1

            result = session.execute(
                update(ModuleCommandState)
                .where(ModuleCommandState.command_name == definition.name)
                .where(
                    or_(
                        ModuleCommandState.lease_owner.is_(None),
                        ModuleCommandState.lease_owner == owner,
                        ModuleCommandState.lease_expires_at.is_(None),
                        ModuleCommandState.lease_expires_at < now,
                    )
                )
                .values(**values)
            )
            session.commit()
            return bool(result.rowcount)
        finally:
            session.close()

    def heartbeat(self, command_name: str, *, owner: str, lease_ttl_seconds: float) -> bool:
        session = self._session()
        now = utc_now_naive()
        lease_expires_at = now + timedelta(seconds=max(1.0, lease_ttl_seconds))
        try:
            result = session.execute(
                update(ModuleCommandState)
                .where(ModuleCommandState.command_name == command_name)
                .where(ModuleCommandState.lease_owner == owner)
                .values(
                    lease_expires_at=lease_expires_at,
                    updated_at=now,
                )
            )
            session.commit()
            return bool(result.rowcount)
        finally:
            session.close()

    def finish_run(
        self,
        command_name: str,
        *,
        owner: str,
        status: str,
        last_error: str | None = None,
        next_run_at: datetime | None = None,
        release_lease: bool = True,
    ) -> None:
        session = self._session()
        now = utc_now_naive()
        try:
            values = {
                "status": status,
                "last_error": last_error,
                "last_finished_at": now,
                "next_run_at": next_run_at,
                "updated_at": now,
            }
            if release_lease:
                values["lease_owner"] = None
                values["lease_expires_at"] = None

            session.execute(
                update(ModuleCommandState)
                .where(ModuleCommandState.command_name == command_name)
                .where(
                    or_(
                        ModuleCommandState.lease_owner == owner,
                        ModuleCommandState.lease_owner.is_(None),
                    )
                )
                .values(**values)
            )
            session.commit()
        finally:
            session.close()


module_command_state_store = ModuleCommandStateStore()
