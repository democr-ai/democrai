from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Optional

from democrai.core.application.knowledge.extractor.base import (
    BaseExtractor,
    ExtractorResult,
    ExtractorSource,
)


class Extractors:
    """Expose extractor discovery and invocation helpers to modules.

    This domain is the public SDK entrypoint for the installable extractor
    runtime. Use it when module code needs to inspect registered extractors,
    resolve the active extractor for a file, or run extraction through the
    sandboxed extractor lifecycle.
    """

    def __init__(self, sdk) -> None:
        """Create the extractors facade for the current SDK instance.

        :param sdk: The request-scoped SDK instance that owns this domain.
        """
        self.sdk = sdk

    def list_manifests(self) -> list[dict[str, Any]]:
        """Return every discovered extractor manifest.

        The payload comes from ``extractors/*/manifest.json`` files discovered
        by the core extractor manifest loader.

        :return: A list of manifest dictionaries.
        """
        from democrai.core.application.knowledge.extractor.manifests import list_extractor_manifests

        return [dict(item) for item in list_extractor_manifests()]

    def list_registered(self) -> list[dict[str, Any]]:
        """Return extractor rows currently present in the registry table.

        This is the operational registry view, not only filesystem discovery.
        It includes runtime status, configured priority, supported extensions,
        and mime types.

        :return: A list of extractor registry rows serialized as dictionaries.
        """
        rows = self.sdk.models.extractor_registry.list(page=0, page_size=500, filters={})
        return list(rows.get("items") or [])

    def list_configurable_mime_bindings(self) -> list[dict[str, Any]]:
        """Return MIME types that can be configured for installed extractors.

        Each row includes the compatible extractor options for that MIME type
        and the currently configured binding, when present.
        """
        from democrai.core.application.knowledge.extractor.bindings import (
            list_configurable_mime_bindings,
        )

        return list_configurable_mime_bindings()

    def list_ingestible_mime_types(self) -> list[str]:
        """Return MIME types currently configured for extraction."""
        from democrai.core.application.knowledge.extractor.bindings import (
            list_ingestible_mime_types,
        )

        return list_ingestible_mime_types()

    def set_mime_type_binding(
        self,
        *,
        mime_type: str,
        extractor_id: str | None,
    ) -> dict[str, Any] | None:
        """Set or clear the extractor binding for one MIME type."""
        from democrai.core.application.knowledge.extractor.bindings import (
            set_mime_type_binding,
        )

        return set_mime_type_binding(
            mime_type=mime_type,
            extractor_id=extractor_id,
        )

    def resolve(
        self,
        *,
        path: str | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the configured extractor for a path, filename, or mime type.

        :param path: Optional filesystem or media-backed path used for extension inference.
        :param filename: Optional filename used when a full path is unavailable.
        :param mime_type: Optional mime type to match explicitly.
        :return: The resolved extractor payload or ``None`` when no valid binding exists.
        """
        from democrai.core.application.knowledge.extractor.resolver import resolve_active_extractor

        resolved_path = str(path or "").strip() or None
        resolved_filename = str(filename or "").strip() or None
        resolved_mime_type = str(mime_type or "").strip().lower() or None
        if resolved_mime_type is None:
            probe = resolved_path or resolved_filename
            if probe:
                resolved_mime_type = self.guess_mime_type(probe)
        return resolve_active_extractor(
            path=resolved_path,
            filename=resolved_filename,
            mime_type=resolved_mime_type,
        )

    def resolve_for_mime_type(self, mime_type: str) -> dict[str, Any] | None:
        """Resolve the active extractor for one mime type.

        :param mime_type: Mime type such as ``application/pdf`` or ``image/png``.
        :return: The resolved extractor payload or ``None``.
        """
        return self.resolve(mime_type=mime_type)

    async def request_install(
        self,
        *,
        extractor_id: str,
        force: bool = False,
        install_config: Optional[dict[str, Any]] = None,
        requested_by: Optional[dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Publish an install request for an extractor."""
        from democrai.core.application.knowledge.extractor.install_events import (
            publish_extractor_install_requested,
        )

        return await publish_extractor_install_requested(
            extractor_id=extractor_id,
            force=force,
            install_config=install_config,
            requested_by=requested_by,
            task_id=task_id,
        )

    async def sync_runtime(self) -> None:
        """Synchronize active extractors with the runtime extractor manager."""
        from democrai.core.application.knowledge.extractor.runtime import (
            get_extractor_runtime,
        )

        await get_extractor_runtime().sync_active_extractors()

    async def check_ready(
        self,
        *,
        extractor_id: str,
    ) -> dict[str, Any]:
        """Return whether an extractor runtime is installed and importable."""
        from democrai.core.application.knowledge.extractor.runtime import (
            check_extractor_ready_runtime,
        )

        return check_extractor_ready_runtime(extractor_id=extractor_id)

    def extract(
        self,
        *,
        path: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
        config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any] | None:
        """Run the active registered extractor selected by extension or mime type.

        Provide either ``path`` or ``data``. When using ``data`` you should also
        provide ``filename`` and, when available, ``mime_type`` so the resolver
        can choose the correct extractor deterministically.

        :param path: Optional filesystem or media-backed path.
        :param data: Optional in-memory payload.
        :param filename: Optional filename used with in-memory payloads.
        :param mime_type: Optional mime type used to disambiguate resolution.
        :param config: Optional runtime configuration overrides for the extractor.
        :return: The extraction payload or ``None`` when no extractor matches.
        """
        from democrai.core.application.knowledge.extractor.resolver import (
            extract_with_active_extractor,
        )

        resolved_path = str(path or "").strip() or None
        resolved_filename = str(filename or "").strip() or None
        resolved_mime_type = str(mime_type or "").strip().lower() or None
        if resolved_mime_type is None:
            probe = resolved_path or resolved_filename
            if probe:
                resolved_mime_type = self.guess_mime_type(probe)
        return extract_with_active_extractor(
            path=resolved_path,
            data=bytes(data) if data is not None else None,
            filename=resolved_filename,
            mime_type=resolved_mime_type,
            config_overrides=config,
        )

    def extract_with_registered(
        self,
        *,
        extractor_id: str,
        path: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
        config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any] | None:
        """Run one installed extractor directly, without MIME binding resolution.

        This is intended for management/test flows where the user selected a
        specific extractor and wants to exercise that runtime directly.
        """
        from democrai.core.application.knowledge.extractor.resolver import (
            extract_with_registered_extractor,
        )

        resolved_extractor_id = str(extractor_id or "").strip().lower()
        if not resolved_extractor_id:
            raise ValueError("extractor_id is required")
        resolved_path = str(path or "").strip() or None
        resolved_filename = str(filename or "").strip() or None
        resolved_mime_type = str(mime_type or "").strip().lower() or None
        if resolved_mime_type is None:
            probe = resolved_path or resolved_filename
            if probe:
                resolved_mime_type = self.guess_mime_type(probe)
        return extract_with_registered_extractor(
            extractor_id=resolved_extractor_id,
            path=resolved_path,
            data=bytes(data) if data is not None else None,
            filename=resolved_filename,
            mime_type=resolved_mime_type,
            config_overrides=config,
        )

    @staticmethod
    def guess_mime_type(path_or_name: str) -> str | None:
        """Guess a mime type from a path or filename.

        :param path_or_name: A path or filename with an extension.
        :return: The normalized mime type, or ``None`` when unknown.
        """
        guessed, _ = mimetypes.guess_type(str(path_or_name or ""))
        return str(guessed or "").strip().lower() or None
