from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.runtime import handles as handles_mod
from democrai.core.application.ai.engine.runtime.handles import create_engine_handle
from democrai.core.application.ai.models.catalog_download import (
    ModelStorageOps,
    _catalog_inventory_extra_config,
    _download_catalog_to_storage,
)
from democrai.core.infrastructure.storage.media.providers.base import MaterializedMedia
from democrai.core.runtime.foundation.app import request_context_scope
from democrai.core.application.ai.engine.schemas.completion import (
    CompletionOptions,
    ContentPart,
    Function,
    Message,
    Tool,
)
from democrai.sdk.engines import get_chat_template
from engines.llamacpp.engine import LlamaCppEngine, _messages_have_images


def _qwen_vision_entry() -> dict:
    return {
        "legacy_model_id": "qwen3.5-0.8b-unsloth-q4-k-m",
        "runtime": {
            "entrypoint": "Qwen3.5-0.8B-Q4_K_M.gguf",
            "auxiliary_artifacts": {"mmproj": "mmproj"},
            "defaults": {"runtime": {"n_ctx": 8192}},
        },
        "artifacts": [
            {
                "id": "weights",
                "required": True,
                "runtime_role": "model",
                "target": "models/Qwen3.5-0.8B-Q4_K_M.gguf",
                "source": {
                    "type": "huggingface",
                    "repo": "unsloth/Qwen3.5-0.8B-GGUF",
                    "files": ["Qwen3.5-0.8B-Q4_K_M.gguf"],
                },
            },
            {
                "id": "mmproj",
                "required": True,
                "runtime_role": "multimodal_projector",
                "target": "models/mmproj-F16.gguf",
                "source": {
                    "type": "huggingface",
                    "repo": "unsloth/Qwen3.5-0.8B-GGUF",
                    "files": ["mmproj-F16.gguf"],
                },
            },
        ],
    }


def test_multimodal_catalog_download_preserves_model_directory_with_dotted_id():
    calls: list[tuple] = []

    def add_model(model_id, *, payload=None, source_path=None, filename=None):
        calls.append(("add_model", model_id, filename, payload, source_path))
        if filename:
            return f"models/{model_id}/{filename}"
        return f"models/{model_id}"

    def add_model_from_source(model_id, *, source, filename=None, progress_callback=None):
        calls.append(("add_model_from_source", model_id, source, filename))
        return f"models/{model_id}"

    entry = _qwen_vision_entry()
    with request_context_scope(
        {
            "request_id": "catalog-download-test",
            "user": 1,
            "organization_id": None,
            "access_level": 1,
            "module_name": "system",
        }
    ):
        storage_ref = asyncio.run(
            _download_catalog_to_storage(
                ModelStorageOps(
                    add_model=add_model,
                    add_model_from_source=add_model_from_source,
                    view=lambda _path: b"",
                    delete=lambda _path: None,
                ),
                name="qwen3.5-0.8b-unsloth-q4-k-m",
                entry=entry,
                task_id=None,
            )
        )
    extra_config = _catalog_inventory_extra_config(entry, storage_ref)

    assert storage_ref == "models/qwen3.5-0.8b-unsloth-q4-k-m"
    assert extra_config["storage_prefix"] == "models/qwen3.5-0.8b-unsloth-q4-k-m"
    assert extra_config["runtime_entrypoint"] == "Qwen3.5-0.8B-Q4_K_M.gguf"
    assert extra_config["auxiliary_artifacts"] == {"mmproj": "mmproj"}
    assert calls[0][2]["target"] == "Qwen3.5-0.8B-Q4_K_M.gguf"
    assert calls[1][2]["target"] == "mmproj-F16.gguf"
    assert calls[2][0] == "add_model"
    assert calls[2][2] == ".democrai-model-manifest.json"


def test_catalog_extra_config_requires_runtime_entrypoint_for_directory_models():
    extra_config = _catalog_inventory_extra_config(
        {
            "legacy_model_id": "gemma-4-26b-a4b-it-unsloth-ud-q4-k-m",
            "runtime": {
                "entrypoint": "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
                "model_ref": "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf",
                "auxiliary_artifacts": {"mmproj": "mmproj"},
            },
        },
        "models/gemma-4-26b-a4b-it-unsloth-ud-q4-k-m",
    )

    assert extra_config["runtime_entrypoint"] == "gemma-4-26B-A4B-it-UD-Q4_K_M.gguf"
    assert (
        extra_config["storage_prefix"]
        == "models/gemma-4-26b-a4b-it-unsloth-ud-q4-k-m"
    )


def test_catalog_runtime_entrypoint_matches_storage_shape():
    missing: list[str] = []
    unexpected: list[str] = []
    for path in sorted(Path("engines").glob("*/models/catalog.json")):
        catalog = json.loads(path.read_text(encoding="utf-8"))
        for model in list(catalog.get("models") or []):
            runtime = model.get("runtime") if isinstance(model, dict) else None
            artifacts = model.get("artifacts") if isinstance(model, dict) else None
            if not isinstance(runtime, dict) or not isinstance(artifacts, list):
                continue
            required_artifact_count = sum(
                1
                for item in artifacts
                if isinstance(item, dict) and item.get("required") is True
            )
            artifact_ref = str(runtime.get("artifact_ref") or "weights").strip()
            artifact = next(
                (
                    item
                    for item in artifacts
                    if isinstance(item, dict)
                    and str(item.get("id") or "").strip() == artifact_ref
                ),
                None,
            )
            if artifact is None:
                artifact = next(
                    (
                        item
                        for item in artifacts
                        if isinstance(item, dict)
                        and str(item.get("runtime_role") or "").strip() == "model"
                    ),
                    None,
                )
            if not isinstance(artifact, dict):
                continue
            source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
            source_files = source.get("files") if isinstance(source, dict) else None
            source_file_count = len(source_files) if isinstance(source_files, list) else 0
            target = str(artifact.get("target") or "").strip().replace("\\", "/")
            if target.startswith("models/"):
                target = target[len("models/") :]
            runtime_entrypoint = str(runtime.get("entrypoint") or "").strip()
            metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
            target_is_file = Path(target).suffix.lower() in {
                ".gguf",
                ".pt",
                ".onnx",
                ".safetensors",
            }
            needs_entrypoint = (
                required_artifact_count > 1
                or bool(metadata.get("multi_shard"))
                or source_file_count > 1
            )
            if target_is_file and needs_entrypoint and not runtime_entrypoint:
                missing.append(f"{path}:{model.get('id')}:{target}")
            if target_is_file and not needs_entrypoint and runtime_entrypoint:
                unexpected.append(f"{path}:{model.get('id')}:{target}")

    assert missing == []
    assert unexpected == []


def test_engine_handle_resolves_model_and_auxiliary_paths_from_storage_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    model_dir = tmp_path / "qwen3.5-0.8b-unsloth-q4-k-m"
    model_dir.mkdir()
    (model_dir / "Qwen3.5-0.8B-Q4_K_M.gguf").write_bytes(b"model")
    (model_dir / "mmproj-F16.gguf").write_bytes(b"mmproj")
    created_configs: list[dict] = []

    class _Media:
        def get_path(self, path, *, destination_dir=None):
            assert path == "models/qwen3.5-0.8b-unsloth-q4-k-m"
            return MaterializedMedia(path=str(model_dir), temporary=False)

    class _Subject:
        def __init__(self, *, engine_id, config):
            del engine_id
            created_configs.append(dict(config))

        def close(self):
            return None

    monkeypatch.setattr(handles_mod, "app_ctx", lambda: SimpleNamespace(media=_Media()))
    monkeypatch.setattr(handles_mod, "EngineWorkerSubject", _Subject)

    handle = create_engine_handle(
        engine_id="llamacpp",
        model_registry_id=7,
        config={
            "model_path": "models/qwen3.5-0.8b-unsloth-q4-k-m",
            "runtime_entrypoint": "Qwen3.5-0.8B-Q4_K_M.gguf",
            "artifacts": _qwen_vision_entry()["artifacts"],
            "auxiliary_artifacts": {"mmproj": "mmproj"},
        },
    )

    assert created_configs[0]["model_path"] == str(
        model_dir / "Qwen3.5-0.8B-Q4_K_M.gguf"
    )
    assert created_configs[0]["auxiliary_paths"] == {
        "mmproj": str(model_dir / "mmproj-F16.gguf")
    }
    handle.close()


def test_llamacpp_formats_image_parts_and_requires_projector_for_images():
    messages = [
        Message(
            role="user",
            content=[
                ContentPart(type="text", text="Describe this."),
                ContentPart(type="image", data=b"image-bytes", mime_type="image/png"),
            ],
        )
    ]

    assert _messages_have_images(messages)
    engine = object.__new__(LlamaCppEngine)
    engine.config = {}
    formatted = engine._format_messages(messages)
    assert formatted[0]["content"][0] == {
        "type": "text",
        "text": "Describe this.",
    }
    assert formatted[0]["content"][1]["type"] == "image_url"
    assert formatted[0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )

    engine = object.__new__(LlamaCppEngine)
    engine.multimodal_chat_handler = None
    with pytest.raises(ValueError, match="llamacpp_multimodal_projector_required"):
        engine._ensure_multimodal_ready(has_images=True)


def test_llamacpp_formats_text_only_content_parts_as_string():
    messages = [
        Message(
            role="user",
            content=[
                ContentPart(type="text", text="Hello "),
                ContentPart(type="text", text="world"),
            ],
        )
    ]

    assert not _messages_have_images(messages)
    engine = object.__new__(LlamaCppEngine)
    engine.config = {}
    formatted = engine._format_messages(messages)

    assert formatted == [{"role": "user", "content": "Hello world"}]


def test_qwen35_vl_template_renders_native_vision_tokens():
    template = get_chat_template("qwen35_vl_thinking")
    assert template is not None

    from jinja2.sandbox import ImmutableSandboxedEnvironment

    rendered = ImmutableSandboxedEnvironment().from_string(template["template"]).render(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this."},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            }
        ],
        add_generation_prompt=True,
        enable_thinking=False,
    )

    assert "<|vision_start|>data:image/png;base64,abc<|vision_end|>" in rendered


def test_qwen35_tool_prompt_merges_with_existing_system_message():
    engine = object.__new__(LlamaCppEngine)
    engine.config = {"chat_template": "qwen35_vl_thinking"}
    messages = [
        Message(role="system", content="Original system."),
        Message(role="user", content="Use tool."),
    ]
    options = CompletionOptions(
        tools=[
            Tool(
                function=Function(
                    name="system_test_echo",
                    description="Echo.",
                    parameters={"type": "object", "properties": {}},
                )
            )
        ]
    )

    formatted = engine._format_messages(messages, options)

    assert [item["role"] for item in formatted] == ["system", "user"]
    assert "# Tools" in formatted[0]["content"]
    assert "Original system." in formatted[0]["content"]


def test_llamacpp_multimodal_stream_sets_chat_handler_before_create(monkeypatch):
    messages = [
        Message(
            role="user",
            content=[
                ContentPart(type="text", text="Describe this."),
                ContentPart(type="image", data=b"image-bytes", mime_type="image/png"),
            ],
        )
    ]
    engine = object.__new__(LlamaCppEngine)
    engine.config = {}
    engine.multimodal_chat_handler = object()
    calls: list[object] = []

    class _LLM:
        chat_handler = None

        def create_chat_completion(self, **_kwargs):
            calls.append(self.chat_handler)
            return [
                {
                    "id": "chunk-1",
                    "choices": [{"delta": {"content": "ok"}, "finish_reason": None}],
                }
            ]

    engine.llm = _LLM()

    chunks = asyncio.run(
        _collect_stream(engine._generate_stream(messages, CompletionOptions()))
    )

    assert calls == [engine.multimodal_chat_handler]
    assert engine.llm.chat_handler is None
    assert chunks[0].delta == "ok"


async def _collect_stream(stream):
    return [item async for item in stream]
