from __future__ import annotations

import asyncio
import contextlib
import json
import os
import threading
import traceback
import uuid
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.ai.engine.runtime.serialization import json_value
from democrai.core.application.ai.engine.runtime.serialization import python_value
from democrai.core.application.knowledge.extractor.manifests import load_extractor_class
from democrai.core.infrastructure.storage.media.providers.base import MaterializedMedia
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx
from democrai.core.runtime.foundation.app import request_context_scope
from democrai.core.runtime.dependencies.extractor_env import extractor_env_context
from democrai.core.runtime.dependencies.extractor_env import isolate_extractor_imports


class _WorkerRuntimeConfig:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = dict(values)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def save(self) -> None:
        return None


def _access_rules(items: list[dict[str, Any]]) -> tuple[AccessManifestRule, ...]:
    rules: list[AccessManifestRule] = []
    for item in items:
        subject = item.get("subject")
        resource = item.get("resource")
        if not isinstance(subject, dict) or not isinstance(resource, dict):
            continue
        rules.append(
            AccessManifestRule(
                subject=AccessSubject.create(
                    str(subject.get("subject_type") or ""),
                    str(subject.get("subject_name") or ""),
                ),
                resource=AccessResource.create(
                    resource_type=str(resource.get("resource_type") or ""),
                    operation=str(resource.get("operation") or ""),
                    target=str(resource.get("target") or ""),
                ),
            )
        )
    return tuple(rules)


async def _collect_result(result: Any) -> Any:
    if asyncio.iscoroutine(result):
        return await result
    if hasattr(result, "__aiter__"):
        items = []
        async for item in result:
            items.append(item)
        return items
    return result


class _ParentMediaProxy:
    def __init__(self) -> None:
        request_fd = int(os.environ["DEMOCRAI_EXTRACTOR_WORKER_PARENT_REQUEST_FD"])
        response_fd = int(os.environ["DEMOCRAI_EXTRACTOR_WORKER_PARENT_RESPONSE_FD"])
        self._writer = os.fdopen(request_fd, "w", encoding="utf-8", buffering=1)
        self._reader = os.fdopen(response_fd, "r", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()

    def _request(self, operation: str, payload: dict[str, Any]) -> Any:
        request_id = uuid.uuid4().hex
        with self._lock:
            self._writer.write(
                json.dumps(
                    json_value(
                        {
                            "id": request_id,
                            "parent_request": True,
                            "operation": operation,
                            "payload": payload,
                        }
                    ),
                    ensure_ascii=True,
                )
                + "\n"
            )
            self._writer.flush()
            while True:
                line = self._reader.readline()
                if not line:
                    raise RuntimeError("extractor_runtime_parent_media_channel_closed")
                response = python_value(json.loads(line))
                if str(response.get("id") or "") != request_id:
                    continue
                if not bool(response.get("ok")):
                    raise RuntimeError(
                        str(response.get("error") or "extractor_runtime_parent_media_error")
                    )
                return response.get("result")

    def load(self, path: str) -> bytes:
        storage_path = str(path or "").strip()
        if not storage_path:
            raise ValueError("storage_path_required")
        return bytes(self._request("media.load", {"storage_path": storage_path}))

    def get_path(
        self,
        path: str,
        *,
        destination_dir: str | None = None,
    ) -> MaterializedMedia:
        storage_path = str(path or "").strip()
        if not storage_path:
            raise ValueError("storage_path_required")
        result = self._request(
            "media.materialize",
            {
                "storage_path": storage_path,
                **(
                    {"destination_dir": str(destination_dir or "")}
                    if destination_dir
                    else {}
                ),
            },
        )
        if not isinstance(result, dict):
            raise RuntimeError("extractor_runtime_materialize_response_invalid")
        return MaterializedMedia(
            path=str(result.get("path") or ""),
            temporary=bool(result.get("temporary")),
        )

    def close(self) -> None:
        for handle in (self._reader, self._writer):
            try:
                handle.close()
            except Exception:
                pass


class _Worker:
    def __init__(self, read_fd: int, write_fd: int) -> None:
        self._reader = os.fdopen(read_fd, "r", encoding="utf-8", buffering=1)
        self._writer = os.fdopen(write_fd, "w", encoding="utf-8", buffering=1)
        self._stack = contextlib.ExitStack()
        self._extractor_cls: Any = None
        self._extractor: Any = None
        self._extractor_id = ""
        self._phase = ""
        self._media_proxy = _ParentMediaProxy()
        app_ctx().media = self._media_proxy

    def _send(self, payload: dict[str, Any]) -> None:
        self._writer.write(json.dumps(json_value(payload), ensure_ascii=True) + "\n")
        self._writer.flush()

    def _require_request_context(self, operation: str) -> None:
        try:
            req_ctx()
        except LookupError as exc:
            raise RuntimeError(f"extractor_{operation}_request_context_required") from exc

    def _init(self, payload: dict[str, Any]) -> None:
        extractor_id = str(payload.get("extractor_id") or "").strip().lower()
        phase = str(payload.get("phase") or "runtime").strip().lower()
        if not extractor_id:
            raise RuntimeError("extractor_id_required")
        self._extractor_id = extractor_id
        self._phase = phase
        runtime_config = dict(payload.get("runtime_config") or {})
        if runtime_config:
            app_ctx().config = _WorkerRuntimeConfig(runtime_config)
        os.environ["DEMOCRAI_EXTRACTOR_WORKER"] = "1"
        self._stack.enter_context(
            process_guard_context(
                subject=extractor_id,
                subject_kind="extractor",
                access=_access_rules(list(payload.get("access") or [])),
                allowed_imports=[
                    str(item).strip()
                    for item in list(payload.get("allowed_imports") or [])
                    if str(item).strip()
                ],
                allow_fork=phase == "install",
                allow_subprocess=phase == "install",
                inherit_parent_access=False,
            )
        )
        env = (
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            }
            if phase == "runtime"
            else None
        )
        self._stack.enter_context(extractor_env_context(extractor_id, env=env))
        isolate_extractor_imports(extractor_id)
        extractor_cls = load_extractor_class(extractor_id)
        if extractor_cls is None:
            raise RuntimeError(f"extractor_runtime_class_not_found:{extractor_id}")
        self._extractor_cls = extractor_cls
        if phase == "runtime":
            self._extractor = extractor_cls(dict(payload.get("config") or {}))

    async def _invoke_class(self, payload: dict[str, Any]) -> Any:
        if self._extractor_cls is None:
            raise RuntimeError("extractor_worker_not_initialized")
        method = payload.get("method")
        if not isinstance(method, str):
            raise RuntimeError("extractor_runtime_method_required")
        if not method:
            raise RuntimeError("extractor_runtime_method_required")
        target = getattr(self._extractor_cls, method, None)
        if target is None:
            raise RuntimeError(f"extractor_runtime_method_not_found:{method}")
        call_payload = payload.get("payload")
        if not isinstance(call_payload, dict):
            raise RuntimeError("extractor_runtime_payload_invalid")
        return await _collect_result(target(**call_payload))

    async def _extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_request_context("extract")
        if self._extractor is None:
            raise RuntimeError("extractor_not_initialized")
        config = payload.get("config")
        if not isinstance(config, dict):
            raise RuntimeError("extractor_config_invalid")
        files = payload.get("files")
        if not isinstance(files, list):
            raise RuntimeError("extractor_files_invalid")
        self._extractor.config(config=config)
        self._extractor.init(*files)
        return {
            "structure": self._extractor.get_structure(),
            "markdown_content": self._extractor.get_markdown_content(),
            "chunks": self._extractor.get_chunks(),
            "index": self._extractor.get_index(),
            "formulas": self._extractor.get_formulas(),
            "tables": self._extractor.get_tables(),
            "images": self._extractor.get_images(),
        }

    async def run(self) -> int:
        while True:
            line = await asyncio.to_thread(self._reader.readline)
            if not line:
                return 0
            if not line.strip():
                continue
            request = python_value(json.loads(line))
            request_id = str(request.get("id") or "")
            try:
                with request_context_scope(dict(request.get("request_context") or {})):
                    operation = str(request.get("operation") or "").strip()
                    payload = dict(request.get("payload") or {})
                    if operation == "init":
                        self._init(payload)
                        self._send({"id": request_id, "ok": True, "result": None})
                        continue
                    if operation == "invoke_class":
                        result = await self._invoke_class(payload)
                        self._send({"id": request_id, "ok": True, "result": result})
                        continue
                    if operation == "extract":
                        result = await self._extract(payload)
                        self._send({"id": request_id, "ok": True, "result": result})
                        continue
                    if operation == "close":
                        self._send({"id": request_id, "ok": True, "result": None})
                        return 0
                    raise RuntimeError(f"extractor_worker_operation_unknown:{operation}")
            except Exception as exc:
                try:
                    app_ctx().logger.error(
                        "[ExtractorWorker] Request failed "
                        f"extractor_id={self._extractor_id} phase={self._phase} "
                        f"operation={request.get('operation', '')} request_id={request_id} "
                        f"error={exc}\n{traceback.format_exc()}"
                    )
                except Exception:
                    pass
                self._send(
                    {
                        "id": request_id,
                        "ok": False,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
        return 0

    def close(self) -> None:
        cleanup = getattr(self._extractor, "cleanup", None)
        if callable(cleanup):
            cleanup()
        self._media_proxy.close()
        self._stack.close()


async def _main() -> int:
    read_fd = int(os.environ["DEMOCRAI_EXTRACTOR_WORKER_READ_FD"])
    write_fd = int(os.environ["DEMOCRAI_EXTRACTOR_WORKER_WRITE_FD"])
    worker = _Worker(read_fd, write_fd)
    try:
        return await worker.run()
    except asyncio.CancelledError:
        return 0
    finally:
        worker.close()


def _run_main() -> int:
    try:
        return int(asyncio.run(_main()) or 0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(_run_main())
