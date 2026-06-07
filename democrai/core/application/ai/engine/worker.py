from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import traceback
from typing import Any

from democrai.core.runtime.ipc.local_binary_payload import LocalBinaryPayloadChannel
from democrai.core.runtime.ipc.local_connection import connect_from_env


_WORKER_LOGGING_CONFIG_KEYS = {
    "logging.provider",
    "logging.url",
    "logging.method",
}


def _json_value(value: Any, **kwargs: Any) -> Any:
    from democrai.core.application.ai.engine.runtime.serialization import json_value

    return json_value(value, **kwargs)


def _python_value(value: Any) -> Any:
    from democrai.core.application.ai.engine.runtime.serialization import python_value

    return python_value(value)


class _WorkerRuntimeConfig:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = {
            key: value
            for key, value in dict(values).items()
            if key in _WORKER_LOGGING_CONFIG_KEYS
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key in _WORKER_LOGGING_CONFIG_KEYS:
            self._values[key] = value

    def save(self) -> None:
        return None


def _payload_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key) or {}
    if not isinstance(value, dict):
        raise TypeError(f"engine_worker_{key}_dict_expected")
    return value


def _payload_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key) or []
    if not isinstance(value, list):
        raise TypeError(f"engine_worker_{key}_list_expected")
    return value


def _access_rules(items: list[dict[str, Any]]):
    from democrai.core.application.access_policy import AccessManifestRule
    from democrai.core.application.access_policy import AccessResource
    from democrai.core.application.access_policy import AccessSubject

    rules: list[AccessManifestRule] = []
    for item in items:
        subject = item.get("subject") if isinstance(item, dict) else None
        resource = item.get("resource") if isinstance(item, dict) else None
        if not isinstance(subject, dict) or not isinstance(resource, dict):
            continue
        rules.append(
            AccessManifestRule(
                subject=AccessSubject.create(
                    subject.get("subject_type", ""),
                    subject.get("subject_name", ""),
                ),
                resource=AccessResource.create(
                    resource_type=resource.get("resource_type", ""),
                    operation=resource.get("operation", ""),
                    target=resource.get("target", ""),
                ),
            )
        )
    return tuple(rules)


def _configure_worker_logging(logging_config: dict[str, Any], log_dir: str) -> None:
    from democrai.core.infrastructure.observability.logger.manager import LoggerManager
    from democrai.core.runtime.foundation.app import app_ctx

    resolved_log_dir = str(log_dir or "").strip()
    if not resolved_log_dir:
        raise RuntimeError("engine_worker_log_dir_required")

    ctx = app_ctx()
    ctx.config = _WorkerRuntimeConfig(logging_config)
    ctx.logger = LoggerManager(log_dir=resolved_log_dir, config=ctx.config)


def _configure_engine_path_overrides(engine_id: str, path_overrides: dict[str, Any]) -> None:
    from democrai.core.runtime.dependencies.engine_env import set_engine_local_path_overrides

    env_path = str(path_overrides.get("env") or "").strip()
    cache_path = str(path_overrides.get("cache") or "").strip()
    config_path = str(path_overrides.get("config") or "").strip()
    tmp_path = str(path_overrides.get("tmp") or "").strip()
    if not all((env_path, cache_path, config_path, tmp_path)):
        raise RuntimeError("engine_worker_path_overrides_required")
    set_engine_local_path_overrides(
        engine_id,
        env_path=env_path,
        cache_path=cache_path,
        config_path=config_path,
        tmp_path=tmp_path,
    )


def _existing_paths(values: list[str]) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for value in values:
        raw = str(value or "").strip()
        if not raw:
            continue
        try:
            real = os.path.realpath(raw)
        except Exception:
            continue
        if real in seen or not os.path.exists(real):
            continue
        seen.add(real)
        paths.append(real)
    return paths


def _worker_landlock_access_paths(
    access,
) -> tuple[list[str], list[str]]:
    read_only: list[str] = []
    read_write: list[str] = []
    for rule in access:
        resource = rule.resource
        if str(resource.resource_type) != "filesystem":
            continue
        target = str(resource.normalized_target or resource.target or "").strip()
        if not target:
            continue
        operation = str(resource.operation)
        if operation in {"create", "modify", "delete"}:
            read_write.append(target)
        elif operation in {"read", "execute"}:
            read_only.append(target)
    return _existing_paths(read_only), _existing_paths(read_write)


def _apply_worker_landlock(
    *,
    enabled: bool,
    access,
    read_only_paths: list[str],
    read_write_paths: list[str],
) -> None:
    if not enabled:
        return
    from democrai.core.infrastructure.sandbox.os.linux.landlock import (
        apply_landlock_filesystem_rules,
        is_landlock_supported,
    )
    if not is_landlock_supported():
        return
    access_ro, access_rw = _worker_landlock_access_paths(access)
    apply_landlock_filesystem_rules(
        read_only_paths=_existing_paths(
            [
                *read_only_paths,
                *access_ro,
            ]
        ),
        read_write_paths=_existing_paths(
            [
                *read_write_paths,
                *access_rw,
            ]
        ),
    )


def _method_payload(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = _python_value(payload)
    if method in {"generate_completion", "generate_stream"}:
        from democrai.core.application.ai.engine.schemas.completion import CompletionOptions
        from democrai.core.application.ai.security.prompt.messages import (
            normalize_prompt_messages,
        )

        messages = data.get("messages")
        options = data.get("options")
        if isinstance(messages, list):
            data["messages"] = normalize_prompt_messages(messages)
        if options is None:
            data["options"] = CompletionOptions()
        elif not isinstance(options, CompletionOptions):
            if not isinstance(options, dict):
                raise TypeError("completion_options_expected")
            data["options"] = CompletionOptions(**options)
    if method in {"synthesize", "synthesize_stream"}:
        from democrai.core.application.ai.engine.schemas.audio import TTSOptions

        options = data.get("options")
        if options is not None and not isinstance(options, TTSOptions):
            if not isinstance(options, dict):
                raise TypeError("tts_options_expected")
            data["options"] = TTSOptions(**options)
    if method == "rerank":
        from democrai.core.application.ai.engine.schemas.completion import RerankOptions

        options = data.get("options")
        if options is not None and not isinstance(options, RerankOptions):
            if not isinstance(options, dict):
                raise TypeError("rerank_options_expected")
            data["options"] = RerankOptions(**options)
    if method == "classify":
        from democrai.core.application.ai.engine.schemas.completion import (
            ClassificationOptions,
        )

        options = data.get("options")
        if options is not None and not isinstance(options, ClassificationOptions):
            if not isinstance(options, dict):
                raise TypeError("classification_options_expected")
            data["options"] = ClassificationOptions(**options)
    if method == "extract_triples":
        from democrai.core.application.ai.engine.schemas.kg import KGExtractionOptions

        options = data.get("options")
        if options is not None and not isinstance(options, KGExtractionOptions):
            if not isinstance(options, dict):
                raise TypeError("kg_extraction_options_expected")
            data["options"] = KGExtractionOptions(**options)
    return data


async def _collect_result(result: Any) -> Any:
    if asyncio.iscoroutine(result):
        return await result
    if hasattr(result, "__aiter__"):
        items = []
        async for item in result:
            items.append(item)
        return items
    return result


async def _stream_items(result: Any):
    if asyncio.iscoroutine(result):
        result = await result
    if hasattr(result, "__aiter__"):
        async for item in result:
            yield item
        return
    if result is not None:
        yield result


async def _send_stream_result(
    worker,
    *,
    response_id: str,
    execution_id: str,
    task: asyncio.Task,
) -> None:
    try:
        result = await task
        async for item in _stream_items(result):
            worker._send({"id": response_id, "stream": "chunk", "chunk": item})
        worker._send({"id": response_id, "stream": "end", "ok": True})
    except asyncio.CancelledError:
        worker._send(
            {
                "id": response_id,
                "stream": "end",
                "ok": False,
                "error": "request_cancelled",
                "cancelled": True,
            }
        )
    except Exception as exc:
        try:
            from democrai.core.runtime.foundation.app import app_ctx

            app_ctx().logger.error(
                "[EngineWorker] Stream task failed "
                f"engine_id={getattr(worker, '_engine_id', '')} "
                f"response_id={response_id} execution_id={execution_id} "
                f"error={exc}\n{traceback.format_exc()}"
            )
        except Exception:
            pass
        worker._send(
            {
                "id": response_id,
                "stream": "end",
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        worker._tasks.pop(execution_id, None)


class _Worker:
    def __init__(self, conn) -> None:
        self._conn = conn
        self._channel = LocalBinaryPayloadChannel(conn)
        self._stack = contextlib.ExitStack()
        self._engine: Any = None
        self._engine_cls: Any = None
        self._engine_id = ""
        self._tasks: dict[str, asyncio.Task] = {}
        self._concurrency_enabled = False
        self._invoke_semaphore = asyncio.Semaphore(1)

    def _send(self, payload: dict[str, Any]) -> None:
        self._channel.send_json(payload, _json_value)

    async def _send_task_result(
        self,
        *,
        response_id: str,
        execution_id: str,
        task: asyncio.Task,
    ) -> None:
        try:
            result = await task
            self._send({"id": response_id, "ok": True, "result": result})
        except asyncio.CancelledError:
            self._send(
                {
                    "id": response_id,
                    "ok": False,
                    "error": "request_cancelled",
                    "cancelled": True,
                }
            )
        except Exception as exc:
            try:
                from democrai.core.runtime.foundation.app import app_ctx

                app_ctx().logger.error(
                    "[EngineWorker] Task failed "
                    f"engine_id={self._engine_id} response_id={response_id} "
                    f"execution_id={execution_id} error={exc}\n{traceback.format_exc()}"
                )
            except Exception:
                pass
            self._send(
                {
                    "id": response_id,
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        finally:
            self._tasks.pop(execution_id, None)

    def _cancel(self, request_id: str) -> bool:
        cancel_hook = getattr(self._engine, "cancel_request", None)
        if callable(cancel_hook):
            cancel_hook(request_id)
        task = self._tasks.get(request_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def _init(self, payload: dict[str, Any]) -> None:
        engine_id = payload.get("engine_id", "")
        if not engine_id:
            raise RuntimeError("engine_id_required")
        self._engine_id = str(engine_id).strip().lower()
        config = _payload_dict(payload, "config")
        concurrency_enabled = config.get("concurrency_enabled", False)
        concurrency_limit = int(config.get("concurrency_limit", 1))
        if concurrency_limit < 1:
            concurrency_limit = 1
        self._concurrency_enabled = concurrency_enabled
        self._invoke_semaphore = asyncio.Semaphore(
            concurrency_limit if concurrency_enabled else 1
        )
        os.environ["DEMOCRAI_ENGINE_WORKER"] = "1"
        access = _access_rules(_payload_list(payload, "access"))
        _configure_worker_logging(
            _payload_dict(payload, "logging_config"),
            str(payload.get("log_dir") or ""),
        )
        _configure_engine_path_overrides(
            self._engine_id,
            _payload_dict(payload, "path_overrides"),
        )
        _apply_worker_landlock(
            enabled=bool(payload.get("landlock_enabled", False)),
            access=access,
            read_only_paths=[
                str(item) for item in _payload_list(payload, "landlock_read_only_paths")
            ],
            read_write_paths=[
                str(item) for item in _payload_list(payload, "landlock_read_write_paths")
            ],
        )
        from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
        from democrai.core.runtime.dependencies.engine_env import engine_env_context
        from democrai.core.runtime.dependencies.engine_env import isolate_engine_imports
        from democrai.core.application.ai.engine.manifests import load_engine_class

        self._stack.enter_context(
            process_guard_context(
                subject=engine_id,
                subject_kind="engine",
                access=access,
                allowed_imports=[
                    item for item in _payload_list(payload, "allowed_imports") if item
                ],
                allowed_subprocess_commands=[
                    item
                    for item in _payload_list(payload, "allowed_subprocess_commands")
                    if item
                ],
                allow_fork=True,
                allow_subprocess=True,
                include_runtime_access=False,
                inherit_parent_access=False,
            )
        )
        self._stack.enter_context(
            engine_env_context(
                engine_id,
                env={
                    key: value for key, value in _payload_dict(payload, "env").items()
                },
            )
        )
        isolate_engine_imports(engine_id)
        engine_cls = load_engine_class(engine_id)
        if engine_cls is None:
            raise RuntimeError(f"engine_runtime_class_not_found:{engine_id}")
        self._engine_cls = engine_cls
        if bool(payload.get("class_only", False)):
            return
        self._engine = engine_cls(config)

    async def _call_engine_method(
        self, target: Any, call_payload: dict[str, Any]
    ) -> Any:
        if self._concurrency_enabled and not (
            inspect.iscoroutinefunction(target) or inspect.isasyncgenfunction(target)
        ):
            return await asyncio.to_thread(target, **call_payload)
        return target(**call_payload)

    async def _invoke(self, payload: dict[str, Any]) -> Any:
        method = payload.get("method", "")
        if not method:
            raise RuntimeError("engine_runtime_method_required")
        subject = self._engine if self._engine is not None else self._engine_cls
        if subject is None:
            raise RuntimeError("engine_not_initialized")
        target = getattr(subject, method, None)
        if target is None:
            raise RuntimeError(f"engine_runtime_method_not_found:{method}")
        raw_payload = _payload_dict(payload, "payload")
        context = raw_payload.pop("__ai_call_context", None)
        call_payload = _method_payload(method, raw_payload)
        async with self._invoke_semaphore:
            if isinstance(context, dict) and context:
                from democrai.core.application.ai.engine.base.llm import ai_call_context

                with ai_call_context(**context):
                    return await _collect_result(
                        await self._call_engine_method(target, call_payload)
                    )
            return await _collect_result(
                await self._call_engine_method(target, call_payload)
            )

    async def _invoke_stream(self, payload: dict[str, Any]) -> Any:
        if self._engine is None:
            raise RuntimeError("engine_not_initialized")
        method = payload.get("method", "")
        if method not in {"generate_stream", "synthesize_stream"}:
            raise RuntimeError(f"engine_runtime_stream_method_not_found:{method}")
        target = getattr(self._engine, method, None)
        if target is None:
            raise RuntimeError(f"engine_runtime_method_not_found:{method}")
        raw_payload = _payload_dict(payload, "payload")
        context = raw_payload.pop("__ai_call_context", None)
        call_payload = _method_payload(method, raw_payload)

        async def _invoke_items():
            async with self._invoke_semaphore:
                if isinstance(context, dict) and context:
                    from democrai.core.application.ai.engine.base.llm import ai_call_context

                    with ai_call_context(**context):
                        result = await self._call_engine_method(target, call_payload)
                        async for item in _stream_items(result):
                            yield item
                    return
                result = await self._call_engine_method(target, call_payload)
                async for item in _stream_items(result):
                    yield item

        return _invoke_items()

    async def run(self) -> int:
        while True:
            try:
                request = await asyncio.to_thread(self._channel.recv)
            except EOFError:
                return 0
            if not isinstance(request, dict):
                raise TypeError("engine_worker_request_dict_expected")
            request = _python_value(request)
            request_id = request.get("id", "")
            try:
                request_context = request.get("request_context") or {}
                if not isinstance(request_context, dict):
                    raise TypeError("engine_worker_request_context_dict_expected")
                from democrai.core.runtime.foundation.app import request_context_scope

                with request_context_scope(request_context):
                    operation = request.get("operation", "")
                    if operation == "init":
                        self._init(_payload_dict(request, "payload"))
                        self._send({"id": request_id, "ok": True, "result": None})
                        continue
                    if operation == "invoke":
                        execution_id = request.get("request_id") or request_id
                        payload = _payload_dict(request, "payload")
                        method = payload.get("method", "")
                        if method in {"generate_stream", "synthesize_stream"}:
                            task = asyncio.create_task(
                                self._invoke_stream(payload),
                                name=f"engine-worker-stream:{execution_id}",
                            )
                            self._tasks[execution_id] = task
                            asyncio.create_task(
                                _send_stream_result(
                                    self,
                                    response_id=request_id,
                                    execution_id=execution_id,
                                    task=task,
                                )
                            )
                        else:
                            task = asyncio.create_task(
                                self._invoke(payload),
                                name=f"engine-worker-invoke:{execution_id}",
                            )
                            self._tasks[execution_id] = task
                            asyncio.create_task(
                                self._send_task_result(
                                    response_id=request_id,
                                    execution_id=execution_id,
                                    task=task,
                                )
                            )
                        continue
                    if operation == "cancel":
                        payload = _payload_dict(request, "payload")
                        self._send(
                            {
                                "id": request_id,
                                "ok": True,
                                "result": self._cancel(payload.get("request_id", "")),
                            }
                        )
                        continue
                    if operation == "close":
                        self._send({"id": request_id, "ok": True, "result": None})
                        return 0
                    raise RuntimeError(f"engine_worker_operation_unknown:{operation}")
            except Exception as exc:
                try:
                    from democrai.core.runtime.foundation.app import app_ctx

                    app_ctx().logger.error(
                        "[EngineWorker] Request failed "
                        f"engine_id={self._engine_id} operation={request.get('operation', '')} "
                        f"request_id={request_id} error={exc}\n{traceback.format_exc()}",
                        name="_LLM",
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
        for task in list(self._tasks.values()):
            task.cancel()
        cleanup = getattr(self._engine, "cleanup", None)
        if callable(cleanup):
            cleanup()
        self._stack.close()
        self._channel.close()


async def _main() -> int:
    from democrai.core.runtime.foundation.app import app_ctx

    app_ctx().dev = os.environ.get("DEMOCRAI_DEV") == "1"
    conn = connect_from_env("DEMOCRAI_ENGINE_WORKER_CONTROL")
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
        return asyncio.run(_main()) or 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(_run_main())
