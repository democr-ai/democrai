from __future__ import annotations

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.runtime.foundation.app import app_ctx


class ObservabilityCoreModel(BaseCoreModel):
    def _session_factory(self):
        provider = getattr(getattr(app_ctx(), "obs_store", None), "provider", None)
        session_factory = getattr(provider, "SessionLocal", None)
        if not callable(session_factory):
            raise RuntimeError(
                "observability core models require a SQLAlchemy observability provider"
            )
        return session_factory

    def create(self, payload):
        raise NotImplementedError(f"{self.name} is read-only")

    def update(self, entity_id, payload):
        raise NotImplementedError(f"{self.name} is read-only")

    def delete(self, entity_id):
        raise NotImplementedError(f"{self.name} is read-only")
