from __future__ import annotations

from democrai.core.application.access_policy import AccessManifestRule


class OwnerModuleAccess:
    """Resolve the module that owns the current execution and its access.

    Skills, MCP servers and tools run fail-closed
    (``inherit_parent_access=False``) but must inherit the *owning module's*
    declared access on top of their own minimal rules. Every request —
    including AI-initiated ones — originates from a module, so the owner is
    the innermost ``module`` frame of the process-guard
    ``subject_access_chain``, falling back to the AI pipeline caller module.
    Components whose API already names the consumer module (MCP runtime)
    resolve access for that name via ``resolve_for``. An execution with no
    resolvable owner module or access is a bug, not a case to paper over:
    resolution fails loudly.
    """

    @classmethod
    def resolve(cls) -> tuple[str, tuple[AccessManifestRule, ...]]:
        """Return ``(module_name, access_rules)`` for the ambient owner."""
        name = cls.resolve_name()
        return name, cls._access_for(name)

    @classmethod
    def resolve_for(cls, name: str) -> tuple[str, tuple[AccessManifestRule, ...]]:
        """Resolve access for an explicitly named owner module.

        Falls back to ambient resolution when ``name`` is empty.
        """
        normalized = str(name or "").strip().lower()
        if not normalized:
            return cls.resolve()
        return normalized, cls._access_for(normalized)

    @classmethod
    def resolve_name(cls) -> str:
        """Return the ambient owner module name (e.g. for network scoping)."""
        name = cls._owner_from_subject_chain()
        if not name:
            name = cls._owner_from_pipeline_context()
        if not name:
            raise RuntimeError("owner_module_unresolved")
        return name

    @classmethod
    def _access_for(cls, name: str) -> tuple[AccessManifestRule, ...]:
        registry_access = cls._registered_module_access(name)
        if registry_access is not None:
            return registry_access
        chain_access = cls._chain_access_for(name)
        if chain_access is not None:
            return chain_access
        raise RuntimeError(f"owner_module_access_unresolved:{name}")

    @staticmethod
    def _owner_from_subject_chain() -> str:
        from democrai.core.infrastructure.sandbox.process_guard import _state

        chain = _state().get("subject_access_chain") or ()
        if not isinstance(chain, (list, tuple)):
            return ""
        for item in reversed(list(chain)):
            if not isinstance(item, dict):
                continue
            if str(item.get("kind") or "").strip().lower() != "module":
                continue
            name = str(item.get("name") or "").strip().lower()
            if name:
                return name
        return ""

    @staticmethod
    def _chain_access_for(name: str) -> tuple[AccessManifestRule, ...] | None:
        from democrai.core.infrastructure.sandbox.process_guard import (
            _access_rules_from_dicts,
            _state,
        )

        chain = _state().get("subject_access_chain") or ()
        if not isinstance(chain, (list, tuple)):
            return None
        for item in reversed(list(chain)):
            if not isinstance(item, dict):
                continue
            if str(item.get("kind") or "").strip().lower() != "module":
                continue
            if str(item.get("name") or "").strip().lower() != name:
                continue
            raw_access = item.get("access")
            if isinstance(raw_access, list):
                return _access_rules_from_dicts(
                    [rule for rule in raw_access if isinstance(rule, dict)]
                )
            return None
        return None

    @staticmethod
    def _owner_from_pipeline_context() -> str:
        from democrai.core.application.ai.pipeline_context import (
            current_ai_pipeline_context,
        )

        context = current_ai_pipeline_context()
        if context is None:
            return ""
        return str(getattr(context, "caller_module", "") or "").strip().lower()

    @staticmethod
    def _registered_module_access(
        name: str,
    ) -> tuple[AccessManifestRule, ...] | None:
        from democrai.core.runtime.foundation.app import app_ctx

        modules = getattr(app_ctx(), "modules", None)
        if modules is None:
            return None
        try:
            registered = modules.get_module(name)
        except Exception:
            return None
        if registered is None:
            return None
        access = getattr(registered, "access", None)
        if access is None:
            return None
        return tuple(access)
