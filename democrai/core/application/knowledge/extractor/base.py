"""Base types for pluggable external knowledge extractors.

The extractor subsystem allows knowledge ingestion to delegate file parsing to
specialized, installable extractors discovered at runtime. These dataclasses and
ABCs define the contracts used by resolver/runtime code.
"""

from __future__ import annotations

import asyncio
import importlib.util
import mimetypes
import shutil
import tempfile
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from democrai.core.application.knowledge.extractor.manifests import get_extractor_manifest


@dataclass(frozen=True)
class ExtractorSource:
    """Descriptor for the source passed to an external extractor."""

    name: str
    source: str
    mime_type: str | None
    data: bytes
    path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractorResult:
    """Structured result returned by an external extractor implementation."""

    source: ExtractorSource
    structure: dict[str, Any] | list[Any]
    markdown_content: str
    chunks: list[dict[str, Any]]
    index: list[dict[str, Any]]
    formulas: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    images: list[dict[str, Any]] = field(default_factory=list)


class BaseExtractor(ABC):
    """Abstract base class implemented by external knowledge extractors."""

    extractor_id = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = dict(config or {})
        self._sources: tuple[ExtractorSource, ...] = ()
        self._results: tuple[ExtractorResult, ...] | None = None

    @classmethod
    def get_manifest(cls) -> dict[str, Any]:
        return get_extractor_manifest(str(getattr(cls, "extractor_id", "") or "")) or {}

    @classmethod
    def get_manifest_version(cls) -> str:
        manifest = cls.get_manifest()
        return str(manifest.get("manifest_version") or "1")

    @classmethod
    def install(
        cls,
        *,
        force: bool = False,
        node_id: str | None = None,
        event_id: str | None = None,
        source_node_id: str | None = None,
        install_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cls._install_local(
            force=force,
            node_id=node_id,
            event_id=event_id,
            source_node_id=source_node_id,
            install_config=install_config,
        )

    @classmethod
    def _install_local(
        cls,
        *,
        force: bool = False,
        node_id: str | None = None,
        event_id: str | None = None,
        source_node_id: str | None = None,
        install_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = cls._invoke_install(force=force, install_config=install_config)
        ready = cls._check_ready_local(node_id=node_id)
        if not bool(ready.get("ready")):
            raise RuntimeError(
                str(
                    ready.get("message") or f"{cls.__name__} is not ready after install"
                )
            )
        payload = dict(result or {})
        payload.setdefault("extractor_id", str(getattr(cls, "extractor_id", "") or ""))
        payload.setdefault("status", "installed")
        payload.setdefault(
            "message", str(ready.get("message") or "Installation completed")
        )
        return payload

    @classmethod
    def check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._check_ready_local(node_id=node_id)

    @classmethod
    def _check_ready_local(cls, *, node_id: str | None = None) -> dict[str, Any]:
        result = cls._invoke_check_ready(node_id=node_id)
        payload = dict(result or {})
        payload.setdefault("extractor_id", str(getattr(cls, "extractor_id", "") or ""))
        payload.setdefault("ready", False)
        payload.setdefault("missing_local", [])
        payload.setdefault("message", "")
        return payload

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        install_config: dict[str, Any] | None = None,
    ) -> None:
        pass

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._build_ready_payload(
            missing_local=cls._default_missing_local(),
            ok_message="Extractor ready",
            error_message="Missing local dependencies",
        )

    @classmethod
    def _invoke_install(
        cls,
        *,
        force: bool,
        install_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        installer = getattr(cls, "_install")
        outcome = installer(force=force, install_config=install_config or {})
        if isinstance(outcome, dict):
            return outcome
        return {}

    @classmethod
    def _invoke_check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        checker = getattr(cls, "_check_ready")
        outcome = checker(node_id=node_id)
        if isinstance(outcome, dict):
            return outcome
        raise RuntimeError("extractor_check_ready_result_invalid")

    @classmethod
    def _default_missing_local(cls) -> list[str]:
        manifest = cls.get_manifest()
        dependencies = (
            manifest.get("dependencies") if isinstance(manifest, dict) else []
        )
        missing_local: list[str] = []
        for dep in dependencies or []:
            if not isinstance(dep, dict):
                continue
            module_name = str(dep.get("module") or "").strip()
            label = str(
                dep.get("label") or dep.get("dependency_key") or module_name
            ).strip()
            check_type = str(dep.get("check_type") or "").strip().lower()
            commands = str(dep.get("commands") or "").strip()
            if check_type == "command_any":
                command_names = [
                    str(item).strip()
                    for item in commands.split(",")
                    if str(item).strip()
                ]
                if command_names and not any(
                    shutil.which(command) for command in command_names
                ):
                    missing_local.append(label or " or ".join(command_names))
                continue
            if module_name and importlib.util.find_spec(module_name) is None:
                missing_local.append(label or module_name)
        return missing_local

    @classmethod
    def _missing_modules(cls, *module_pairs: tuple[str, str] | str) -> list[str]:
        missing_local: list[str] = []
        for item in module_pairs:
            if isinstance(item, tuple):
                module_name, label = item
            else:
                module_name, label = item, item
            resolved_module = str(module_name or "").strip()
            resolved_label = str(label or resolved_module).strip() or resolved_module
            if resolved_module and importlib.util.find_spec(resolved_module) is None:
                missing_local.append(resolved_label)
        return missing_local

    @classmethod
    def _build_ready_payload(
        cls,
        *,
        missing_local: list[str] | None = None,
        ok_message: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        resolved_missing_local = list(missing_local or [])
        ready = not resolved_missing_local
        return {
            "ready": ready,
            "missing_local": resolved_missing_local,
            "message": str(
                ok_message or "Extractor ready"
                if ready
                else error_message or "Missing local dependencies"
            ),
        }

    def config(
        self, config: dict[str, Any] | None = None, **kwargs: Any
    ) -> "BaseExtractor":
        merged = dict(self._config)
        if config:
            merged.update(config)
        if kwargs:
            merged.update(kwargs)
        self._config = merged
        self._results = None
        return self

    def init(self, *files: Any) -> "BaseExtractor":
        self._sources = self._normalize_sources(files)
        self._results = None
        return self

    def get_structure(self) -> list[dict[str, Any] | list[Any]]:
        return [result.structure for result in self._ensure_results()]

    def get_chunks(self) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for result in self._ensure_results():
            chunks.extend(result.chunks)
        return chunks

    def get_markdown_content(self) -> str:
        sections: list[str] = []
        for result in self._ensure_results():
            title = result.source.name or result.source.source or "document"
            body = str(result.markdown_content or "").strip()
            if not body:
                continue
            sections.append(f"# {title}\n\n{body}")
        return "\n\n---\n\n".join(sections).strip()

    def get_index(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for result in self._ensure_results():
            items.extend(result.index)
        return items

    def get_formulas(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for result in self._ensure_results():
            items.extend(result.formulas)
        return items

    def get_tables(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for result in self._ensure_results():
            items.extend(result.tables)
        return items

    def get_images(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for result in self._ensure_results():
            items.extend(result.images)
        return items

    def _ensure_results(self) -> tuple[ExtractorResult, ...]:
        if not self._sources:
            raise RuntimeError("extractor_not_initialized")
        if self._results is None:
            self._results = tuple(
                self._extract_source(source) for source in self._sources
            )
        return self._results

    @abstractmethod
    def _extract_source(self, source: ExtractorSource) -> ExtractorResult:
        raise NotImplementedError

    def _normalize_sources(self, files: Sequence[Any]) -> tuple[ExtractorSource, ...]:
        flattened: list[Any] = []
        for item in files:
            if isinstance(item, (list, tuple)):
                flattened.extend(item)
            else:
                flattened.append(item)
        sources = [self._resolve_source(item) for item in flattened if item is not None]
        if not sources:
            raise ValueError("extractor_requires_at_least_one_file")
        return tuple(sources)

    def _resolve_source(self, item: Any) -> ExtractorSource:
        if isinstance(item, ExtractorSource):
            return item
        if isinstance(item, (bytes, bytearray)):
            payload = bytes(item)
            return ExtractorSource(
                name="inline.bin",
                source="inline-bytes",
                mime_type=None,
                data=payload,
                metadata={"inline": True},
            )
        if isinstance(item, dict):
            if "bytes" in item and item["bytes"] is not None:
                payload = bytes(item["bytes"])
                name = str(item.get("name") or "inline.bin")
                mime_type = self._normalize_mime_type(
                    item.get("mime_type"), file_name=name
                )
                return ExtractorSource(
                    name=name,
                    source=str(item.get("source") or "inline-bytes"),
                    mime_type=mime_type,
                    data=payload,
                    metadata=dict(item.get("metadata") or {}),
                )
            candidate = item.get("path") or item.get("media_path") or item.get("source")
            if candidate:
                return self._resolve_source(str(candidate))

        candidate = Path(str(item))
        if candidate.is_absolute() and candidate.exists():
            payload = candidate.read_bytes()
            return ExtractorSource(
                name=candidate.name,
                source=str(candidate),
                mime_type=self._normalize_mime_type(None, file_name=candidate.name),
                data=payload,
                path=candidate,
                metadata={"kind": "filesystem"},
            )

        media_path = str(item)
        payload = self._sdk().media.view(media_path)
        name = Path(media_path).name or "media.bin"
        return ExtractorSource(
            name=name,
            source=media_path,
            mime_type=self._normalize_mime_type(None, file_name=name),
            data=payload,
            metadata={"kind": "media"},
        )

    @staticmethod
    def _normalize_mime_type(
        mime_type: str | None, *, file_name: str | None = None
    ) -> str | None:
        normalized = str(mime_type or "").strip()
        if normalized:
            return normalized
        if not file_name:
            return None
        guessed, _ = mimetypes.guess_type(file_name)
        return guessed

    @staticmethod
    def _chunk_text(
        text: str,
        *,
        chunk_size: int = 1200,
        overlap: int = 150,
        source_name: str = "",
    ) -> list[dict[str, Any]]:
        normalized = str(text or "").strip()
        if not normalized:
            return []
        safe_chunk_size = max(1, int(chunk_size or 1200))
        safe_overlap = max(0, min(int(overlap or 0), safe_chunk_size - 1))
        items: list[dict[str, Any]] = []
        start = 0
        index = 0
        while start < len(normalized):  # pragma: no branch
            end = min(len(normalized), start + safe_chunk_size)
            chunk = normalized[start:end].strip()
            if chunk:
                items.append(
                    {
                        "id": f"{source_name or 'chunk'}:{index}",
                        "text": chunk,
                        "start": start,
                        "end": end,
                        "source": source_name,
                    }
                )
                index += 1
            if end >= len(normalized):
                break
            start = max(0, end - safe_overlap)
        return items

    @staticmethod
    def _build_simple_index(
        title: str,
        *,
        chunks: Iterable[dict[str, Any]],
        source: str,
    ) -> list[dict[str, Any]]:
        items = list(chunks)
        return [
            {
                "id": f"{source}:root",
                "title": title,
                "level": 1,
                "source": source,
                "chunk_ids": [item.get("id") for item in items if item.get("id")],
            }
        ]

    @staticmethod
    def _materialize_source_to_path(
        source: ExtractorSource, *, suffix: str | None = None
    ) -> Path:
        if source.path is not None:
            return source.path
        effective_suffix = suffix
        if effective_suffix is None:
            effective_suffix = Path(source.name).suffix or ""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=effective_suffix or "")
        try:
            tmp.write(source.data)
            tmp.flush()
        finally:
            tmp.close()
        return Path(tmp.name)

    @staticmethod
    def _run_async(coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        holder: dict[str, Any] = {}

        def _runner() -> None:
            try:
                holder["result"] = asyncio.run(coro)
            except Exception as exc:
                holder["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "error" in holder:
            raise holder["error"]
        return holder.get("result")

    @staticmethod
    def _sdk() -> Any:
        from democrai.sdk.client import active_sdk

        return active_sdk
