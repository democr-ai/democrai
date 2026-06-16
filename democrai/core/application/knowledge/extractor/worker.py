from __future__ import annotations

import asyncio
import contextlib
import os
import threading
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from democrai.core.runtime.ipc.local_binary_payload import LocalBinaryPayloadChannel
from democrai.core.runtime.ipc.local_connection import connect_from_env


class _WorkerRuntimeConfig:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = dict(values)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def save(self) -> None:
        return None


def _json_value(value: Any, **kwargs: Any) -> Any:
    from democrai.core.application.ai.engine.runtime.serialization import json_value

    return json_value(value, **kwargs)


def _python_value(value: Any) -> Any:
    from democrai.core.application.ai.engine.runtime.serialization import python_value

    return python_value(value)


@dataclass(frozen=True)
class _RuntimeMaterializedMedia:
    path: str
    temporary: bool = False

    def cleanup(self) -> None:
        if not self.temporary:
            return
        target = Path(self.path)
        try:
            if target.is_dir():
                import shutil

                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
        except OSError:
            pass


def _access_rules(items: list[dict[str, Any]]):
    from democrai.core.application.access_policy import AccessManifestRule
    from democrai.core.application.access_policy import AccessResource
    from democrai.core.application.access_policy import AccessSubject

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


def _configure_extractor_path_overrides(
    extractor_id: str,
    path_overrides: dict[str, Any],
) -> None:
    from democrai.core.runtime.dependencies.extractor_env import (
        set_extractor_local_path_overrides,
    )

    env_path = str(path_overrides.get("env") or "").strip()
    cache_path = str(path_overrides.get("cache") or "").strip()
    config_path = str(path_overrides.get("config") or "").strip()
    tmp_path = str(path_overrides.get("tmp") or "").strip()
    if not all((env_path, cache_path, config_path, tmp_path)):
        raise RuntimeError("extractor_worker_path_overrides_required")
    set_extractor_local_path_overrides(
        extractor_id,
        env_path=env_path,
        cache_path=cache_path,
        config_path=config_path,
        tmp_path=tmp_path,
    )


async def _collect_result(result: Any) -> Any:
    if asyncio.iscoroutine(result):
        return await result
    if hasattr(result, "__aiter__"):
        items = []
        async for item in result:
            items.append(item)
        return items
    return result


class _ParentBridge:
    def __init__(self) -> None:
        self._conn = connect_from_env("DEMOCRAI_EXTRACTOR_WORKER_PARENT")
        self._channel = LocalBinaryPayloadChannel(self._conn)
        self._lock = threading.Lock()

    def request(self, operation: str, payload: dict[str, Any]) -> Any:
        request_id = uuid.uuid4().hex
        try:
            from democrai.core.runtime.foundation.app import (
                current_request_context_payload,
            )

            request_context = current_request_context_payload(
                f"extractor_worker_parent.{operation}"
            )
        except Exception:
            request_context = {}
        with self._lock:
            self._channel.send_json(
                {
                    "id": request_id,
                    "parent_request": True,
                    "operation": operation,
                    "payload": payload,
                    "request_context": request_context,
                },
                _json_value,
            )
            while True:
                response = _python_value(self._channel.recv())
                if str(response.get("id") or "") != request_id:
                    continue
                if not bool(response.get("ok")):
                    raise RuntimeError(
                        str(response.get("error") or "extractor_runtime_parent_error")
                    )
                return response.get("result")

    def load(self, path: str) -> bytes:
        storage_path = str(path or "").strip()
        if not storage_path:
            raise ValueError("storage_path_required")
        return bytes(self.request("media.load", {"storage_path": storage_path}))

    def get_path(
        self,
        path: str,
        *,
        destination_dir: str | None = None,
    ) -> _RuntimeMaterializedMedia:
        storage_path = str(path or "").strip()
        if not storage_path:
            raise ValueError("storage_path_required")
        result = self.request(
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
        return _RuntimeMaterializedMedia(
            path=str(result.get("path") or ""),
            temporary=bool(result.get("temporary")),
        )

    def close(self) -> None:
        self._channel.close()
        try:
            self._conn.close()
        except Exception:
            pass


class _ParentMediaSDK:
    def __init__(self, bridge: _ParentBridge) -> None:
        self._bridge = bridge

    def view(self, path: str) -> bytes:
        return self._bridge.load(path)

    def get_path(
        self,
        path: str,
        *,
        destination_dir: str | None = None,
    ) -> _RuntimeMaterializedMedia:
        return self._bridge.get_path(path, destination_dir=destination_dir)


class _ParentEngineProviderProxy:
    def __init__(self, bridge: _ParentBridge, provider_ref: dict[str, Any]) -> None:
        self._bridge = bridge
        self._provider_ref = dict(provider_ref)

    async def _invoke(self, method: str, kwargs: dict[str, Any]) -> Any:
        return await asyncio.to_thread(
            self._bridge.request,
            "ai.invoke_provider",
            {
                "provider_ref": self._provider_ref,
                "method": method,
                "kwargs": kwargs,
            },
        )

    async def generate_completion(self, **kwargs: Any) -> Any:
        return await self._invoke("generate_completion", dict(kwargs))

    async def transcribe(self, *, media_storage_path=None, language=None):
        if not media_storage_path:
            raise RuntimeError("engine_invocation_media_storage_path_required")
        return await self._invoke(
            "transcribe",
            {"language": language, "media_storage_path": media_storage_path},
        )

    async def generate_stream(self, **kwargs: Any):
        items = await self._invoke("generate_stream", dict(kwargs))
        for item in list(items or []):
            yield item

    async def cancel(self, request_id: str) -> bool:
        return bool(
            await asyncio.to_thread(
                self._bridge.request,
                "ai.cancel_request",
                {"request_id": str(request_id or "")},
            )
        )


class _ParentAIProxy:
    def __init__(self, bridge: _ParentBridge) -> None:
        self._bridge = bridge

    async def get_provider_by_model_registry_id(
        self,
        model_registry_id: int | str,
        *,
        confirm_swap: bool = False,
    ) -> dict[str, Any]:
        result = await asyncio.to_thread(
            self._bridge.request,
            "ai.get_provider_by_model_registry_id",
            {
                "model_registry_id": int(model_registry_id),
                "confirm_swap": bool(confirm_swap),
            },
        )
        return self._provider_result(result)

    async def get_provider_for_objective(
        self,
        objective: str,
        *,
        required_capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
    ) -> dict[str, Any]:
        result = await asyncio.to_thread(
            self._bridge.request,
            "ai.get_provider_for_objective",
            {
                "objective": str(objective or ""),
                "required_capabilities": list(required_capabilities or []),
                "prefer_local": prefer_local,
            },
        )
        return self._provider_result(result)

    def cancel_request(self, request_id: str) -> bool:
        return bool(
            self._bridge.request(
                "ai.cancel_request",
                {"request_id": str(request_id or "")},
            )
        )

    def _provider_result(self, result: Any) -> dict[str, Any]:
        payload = dict(result or {}) if isinstance(result, dict) else {}
        provider_ref = payload.pop("provider_ref", None)
        if payload.get("status") == "ok" and isinstance(provider_ref, dict):
            payload["provider"] = _ParentEngineProviderProxy(self._bridge, provider_ref)
        return payload


class _WorkerSDK:
    def __init__(self, bridge: _ParentBridge) -> None:
        self.module_name = "extractor"
        self.session = {}
        self.ai = _ParentAIProxy(bridge)
        self.media = _ParentMediaSDK(bridge)


class _Worker:
    def __init__(self, conn) -> None:
        self._conn = conn
        self._channel = LocalBinaryPayloadChannel(conn)
        self._stack = contextlib.ExitStack()
        self._extractor_cls: Any = None
        self._extractor: Any = None
        self._extractor_id = ""
        self._phase = ""
        self._parent_bridge = _ParentBridge()
        self._previous_default_sdk: Any = None
        from democrai.core.runtime.foundation.app import app_ctx
        import democrai.sdk.client as sdk_client

        app_ctx().media = self._parent_bridge
        self._previous_default_sdk = getattr(sdk_client, "_default_sdk", None)
        sdk_client._default_sdk = _WorkerSDK(self._parent_bridge)

    def _send(self, payload: dict[str, Any]) -> None:
        self._channel.send_json(payload, _json_value)

    def _require_request_context(self, operation: str) -> None:
        from democrai.core.runtime.foundation.app import req_ctx

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
            from democrai.core.runtime.foundation.app import app_ctx

            app_ctx().config = _WorkerRuntimeConfig(runtime_config)
        os.environ["DEMOCRAI_EXTRACTOR_WORKER"] = "1"
        _configure_extractor_path_overrides(
            extractor_id,
            dict(payload.get("path_overrides") or {}),
        )
        from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
        from democrai.core.infrastructure.sandbox.runtime_access_baseline import (
            RuntimeAccessBaseline,
        )
        from democrai.core.runtime.dependencies.extractor_env import extractor_env_context
        from democrai.core.runtime.dependencies.extractor_env import isolate_extractor_imports
        from democrai.core.application.knowledge.extractor.manifests import (
            load_extractor_class,
        )

        # The guard below runs with inherit_parent_access=False, so the
        # launch state's runtime access is dropped; the worker recomputes the
        # python-runtime baseline under its own venv interpreter.
        access = [
            *_access_rules(list(payload.get("access") or [])),
            *RuntimeAccessBaseline.python_runtime_rules(
                subject_kind="extractor",
                subject_name=extractor_id,
            ),
        ]
        self._stack.enter_context(
            process_guard_context(
                subject=extractor_id,
                subject_kind="extractor",
                access=access,
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
        env_payload = payload.get("env")
        env = dict(env_payload) if isinstance(env_payload, dict) else None
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
            try:
                request = _python_value(await asyncio.to_thread(self._channel.recv))
            except EOFError:
                return 0
            request_id = str(request.get("id") or "")
            try:
                from democrai.core.runtime.foundation.app import request_context_scope

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
                    from democrai.core.runtime.foundation.app import app_ctx

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
        try:
            import democrai.sdk.client as sdk_client

            sdk_client._default_sdk = self._previous_default_sdk
        except Exception:
            pass
        self._parent_bridge.close()
        self._stack.close()
        self._channel.close()


async def _main() -> int:
    conn = connect_from_env("DEMOCRAI_EXTRACTOR_WORKER_CONTROL")
    worker = _Worker(conn)
    try:
        return await worker.run()
    except asyncio.CancelledError:
        return 0
    finally:
        worker.close()
        conn.close()


def _run_main() -> int:
    try:
        return int(asyncio.run(_main()) or 0)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(_run_main())
