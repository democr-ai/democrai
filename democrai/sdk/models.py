from __future__ import annotations

from typing import Any

from democrai.core.application.models import CoreModelContext, build_core_model
from democrai.core.application.session_keys import SessionKey
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.platform.utils.identity import to_optional_int


_ALLOWED_MODEL_METHODS = {
    "view",
    "count",
    "all",
    "list",
    "create",
    "update",
    "delete",
    "verify",
    "get_info",
    "get_info_by_id",
    "form_model_create",
    "form_model_update",
    "form_model_extra",
    "filters_model",
    "table_model",
}


class _CoreModelProxy:
    """Module-safe proxy around a single named core model."""

    def __init__(self, sdk_instance: Any, model_name: str):
        """Create a proxy for one core model name."""
        self._sdk = sdk_instance
        self._model_name = model_name

    def _ctx(self, *, bypass: bool = False) -> CoreModelContext:
        """Build the core-model context from the current SDK session."""
        session = self._sdk.session or {}
        user = session.get(SessionKey.USER) or {}
        return CoreModelContext(
            user_id=to_optional_int(user.get("id")) or 0,
            organization_id=to_optional_int(user.get("organization_id")),
            access_level=int(user.get("access_level") or 3),
            module_name=str(self._sdk.module_name or ""),
            session=dict(session),
            bypass=bool(bypass),
        )

    def _resolve(self, *, policy: str = "enforced"):
        """Resolve the actual core model instance for the current request context."""
        normalized_policy = str(policy or "enforced").strip().lower()
        bypass = normalized_policy == "bypass"
        if bypass:
            allow = bool((self._sdk.session or {}).get("_models_bypass"))
            if not allow and not bool(getattr(app_ctx(), "setup_mode", False)):
                raise PermissionError("models bypass policy denied")
        return build_core_model(self._model_name, self._ctx(bypass=bypass))

    def view(self, entity_id: int, *, policy: str = "enforced"):
        """Return one entity by id."""
        return self._resolve(policy=policy).view(entity_id)

    def count(
        self,
        *,
        filters: dict[str, Any] | None = None,
        policy: str = "enforced",
    ):
        """Count entities matching the provided filters."""
        return self._resolve(policy=policy).count(filters=filters)

    def all(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
        policy: str = "enforced",
    ):
        """Return all rows matching filters and sort without pagination."""
        return self._resolve(policy=policy).all(
            filters=filters,
            sort=sort,
        )

    def list(
        self,
        *,
        page: int = 0,
        page_size: int = 25,
        filters: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
        policy: str = "enforced",
    ):
        """List rows with pagination, filters, and optional sorting."""
        return self._resolve(policy=policy).list(
            page=page,
            page_size=page_size,
            filters=filters,
            sort=sort,
        )

    def create(self, payload: dict[str, Any], *, policy: str = "enforced"):
        """Create a new entity through the core model."""
        return self._resolve(policy=policy).create(payload)

    def update(
        self,
        entity_id: int,
        payload: dict[str, Any],
        *,
        policy: str = "enforced",
    ):
        """Update an entity by id through the core model."""
        return self._resolve(policy=policy).update(entity_id, payload)

    def delete(self, entity_id: int, *, policy: str = "enforced"):
        """Delete an entity by id through the core model."""
        return self._resolve(policy=policy).delete(entity_id)

    def verify(self, username: str, password: str, *, policy: str = "enforced"):
        """Run model-specific credential verification."""
        return self._resolve(policy=policy).verify(username, password)

    def get_info(self, username: str, *, policy: str = "enforced"):
        """Return model information by username or natural key."""
        return self._resolve(policy=policy).get_info(username)

    def get_info_by_id(self, user_id: int, *, policy: str = "enforced"):
        """Return model information by entity id."""
        return self._resolve(policy=policy).get_info_by_id(user_id)

    def form_model_create(self, *, policy: str = "enforced"):
        """Return the creation form model declared by the core model."""
        return self._resolve(policy=policy).form_model_create()

    def form_model_update(self, entity_id: int, *, policy: str = "enforced"):
        """Return the update form model for a specific entity."""
        return self._resolve(policy=policy).form_model_update(entity_id)

    def form_model_extra(self, name: str, *, policy: str = "enforced"):
        """Return a named extra form model exposed by the core model."""
        return self._resolve(policy=policy).form_model_extra(name)

    def filters_model(self, *, policy: str = "enforced"):
        """Return the allowed-filters schema for the model."""
        return self._resolve(policy=policy).filters_model()

    def table_model(self, *, policy: str = "enforced"):
        """Return the table schema exposed by the core model."""
        return self._resolve(policy=policy).table_model()

    def __getattr__(self, item: str):
        if item in _ALLOWED_MODEL_METHODS:
            return object.__getattribute__(self, item)
        raise AttributeError(
            f"Core model '{self._model_name}' does not expose '{item}'"
        )


class CoreModelsSDK:
    """Lazy namespace that exposes core models as attributes."""

    def __init__(self, sdk_instance: Any):
        """Create the core-model namespace for the current SDK instance."""
        self._sdk = sdk_instance
        self._cache: dict[str, _CoreModelProxy] = {}

    def __getattr__(self, model_name: str) -> _CoreModelProxy:
        """Return a lazily created proxy for the named core model."""
        normalized_name = str(model_name or "").strip().lower()
        if not normalized_name:
            raise AttributeError("Invalid core model name")
        if normalized_name not in self._cache:
            self._cache[normalized_name] = _CoreModelProxy(
                self._sdk,
                normalized_name,
            )
        return self._cache[normalized_name]
