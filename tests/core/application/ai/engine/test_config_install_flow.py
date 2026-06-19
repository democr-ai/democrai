from __future__ import annotations

import asyncio
from types import SimpleNamespace

from democrai.core.application.ai.engine import config_install
from democrai.core.application.ai.engine.config_install import (
    _all_rows,
    install_engines_from_config,
)


class FakeModelProxy:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.next_id = 1 + max([int(row.get("id") or 0) for row in self.rows] or [0])

    def all(self):
        return {"rows": [dict(row) for row in self.rows]}

    def create(self, payload):
        row = {"id": self.next_id, **payload}
        self.next_id += 1
        self.rows.append(row)
        return dict(row)

    def update(self, entity_id, payload):
        for row in self.rows:
            if int(row["id"]) == int(entity_id):
                row.update(payload)
                return dict(row)
        raise KeyError(entity_id)

    def view(self, entity_id):
        for row in self.rows:
            if int(row["id"]) == int(entity_id):
                return dict(row)
        return None

    def delete(self, entity_id):
        self.rows = [row for row in self.rows if int(row["id"]) != int(entity_id)]
        return {"deleted": True}


class FakeModels:
    def __init__(self):
        self.engine_registry = FakeModelProxy()
        self.model_registry = FakeModelProxy()
        self.available_model_registry = FakeModelProxy()


class FakeTaskManager:
    def __init__(self):
        self.tasks = {}

    def submit_external_sync(self, user_id, label, module="core", organization_id=None, task_key=None):
        task_id = f"task-{len(self.tasks) + 1}"
        self.tasks[task_id] = SimpleNamespace(id=task_id, progress=0.0, status="running")
        return task_id, True

    def complete_external_sync(self, task_id, result=None):
        self.tasks[task_id].progress = 1.0
        self.tasks[task_id].status = "completed"
        return True

    def fail_external_sync(self, task_id, error):
        self.tasks[task_id].status = "failed"
        self.tasks[task_id].error = error
        return True

    def get_task(self, task_id):
        return self.tasks.get(task_id)


class FakeEngines:
    def __init__(self, models):
        self.models = models
        self.calls = []
        self.catalog = {
            "llamacpp": [
                {
                    "id": "tiny-local",
                    "model_id": "tiny-local",
                    "label": "Tiny local",
                    "source_kind": "engine_catalog",
                    "capabilities": ["chat"],
                    "runtime": {"model_ref": "tiny-local"},
                }
            ]
        }
        self.available_by_engine = {
            "openai": [
                {
                    "id": "gpt-5.2",
                    "model_id": "gpt-5.2",
                    "label": "GPT",
                    "source_kind": "provider_api",
                    "capabilities": ["chat"],
                }
            ],
            "ollama": [
                {
                    "id": "llama3.2",
                    "model_id": "llama3.2",
                    "label": "Llama",
                    "source_kind": "provider_api",
                    "capabilities": ["chat"],
                }
            ],
        }

    async def provider_requirements(self, *, provider_id):
        return {
            "provider": provider_id,
            "supported": True,
            "configurable": provider_id in {"openai", "ollama"},
            "support_reason": "",
        }

    async def check_runtime_config(self, *, engine_id, config=None):
        return {"valid": True}

    async def begin_install(self, *, engine_registry_id, force=False, requested_by=None, task_id=None):
        self.calls.append(("begin_install", engine_registry_id, task_id))
        self.models.engine_registry.update(engine_registry_id, {"status": "installed"})
        return {"status": "installing"}

    async def install_status(self, *, engine_registry_id):
        return {"status": "installed"}

    async def activate_instance(self, *, engine_registry_id):
        self.calls.append(("activate_instance", engine_registry_id))
        self.models.engine_registry.update(engine_registry_id, {"status": "active"})
        return {"status": "active"}

    async def stop_engine(self, *, engine_registry_id):
        self.calls.append(("stop_engine", engine_registry_id))
        return {"status": "ok", "stopped": True}

    async def sync_runtime(self):
        self.calls.append(("sync_runtime",))

    async def list_available_models(self, *, engine_id):
        engine = next(
            row for row in self.models.engine_registry.rows if int(row["id"]) == int(engine_id)
        )
        provider_rows = self.available_by_engine.get(engine["provider"], [])
        inventory = [
            row
            for row in self.models.available_model_registry.rows
            if row.get("provider_hint") == engine["provider"]
        ]
        return [dict(row) for row in [*provider_rows, *inventory]]

    async def list_models(self, *, engine_id):
        return [
            dict(row)
            for row in self.models.model_registry.rows
            if int(row.get("engine_id") or 0) == int(engine_id)
        ]

    async def list_catalog_models(self, *, engine_id):
        return [dict(row) for row in self.catalog.get(engine_id, [])]

    async def download_model(self, *, catalog_id, confirmed_resource_warning=False, task_id=None):
        if task_id is None:
            return {"status": "ready", "catalog_id": catalog_id}
        row = self.models.available_model_registry.create(
            {
                "name": catalog_id,
                "label": "Tiny local",
                "catalog_model_id": catalog_id,
                "provider_hint": "llamacpp",
                "format": "gguf",
                "status": "available",
                "source_kind": "catalog",
                "storage_ref": f"models/{catalog_id}",
                "capabilities": ["chat"],
                "extra_config": {
                    "runtime_model_ref": "tiny-local",
                    "defaults": {
                        "generation": {"temperature": 0.2},
                        "runtime": {"context_length": 2048},
                    },
                    "options_schema": {"fields": []},
                    "features": {"tool_calling": {"supported": True}},
                },
            }
        )
        return {"status": "available", "row": row, "storage_ref": row["storage_ref"]}

    async def delete_available_model(self, *, available_model_id):
        self.models.available_model_registry.delete(available_model_id)
        return {"deleted": True}


class FakeSDK:
    def __init__(self):
        self.models = FakeModels()
        self.engines = FakeEngines(self.models)


def _run(coro):
    return asyncio.run(coro)


def test_all_rows_reads_core_model_all_rows_payload():
    proxy = FakeModelProxy([{"id": 1, "name": "engine"}])

    assert _all_rows(proxy) == [{"id": 1, "name": "engine"}]


def test_engine_create_install_activate_and_remote_model(monkeypatch):
    sdk = FakeSDK()
    events = []

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "openai",
                        "name": "openai-main",
                        "config": {"api_key": "secret"},
                        "models": [{"id": "gpt-5.2"}],
                    }
                ]
            },
            reset_mode="keep",
            yes=False,
            progress=events.append,
        )
    )

    assert report.errors == []
    assert sdk.models.engine_registry.rows[0]["name"] == "openai-main"
    assert sdk.models.engine_registry.rows[0]["provider"] == "openai"
    assert sdk.models.engine_registry.rows[0]["config"] == {"api_key": "secret"}
    assert report.installed_engines[0]["name"] == "openai-main"
    assert report.activated_engines[0]["name"] == "openai-main"
    assert report.activated_models[0]["model_id"] == "gpt-5.2"
    assert ("sync_runtime",) in sdk.engines.calls
    assert any(event["status"] == "active" for event in events)


def test_existing_engine_updates_config_and_two_instances():
    sdk = FakeSDK()
    sdk.models.engine_registry.create(
        {
            "name": "ollama-a",
            "provider": "ollama",
            "config": {"base_url": "old"},
            "status": "uninstalled",
            "supported": True,
        }
    )

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "ollama",
                        "instances": [
                            {
                                "name": "ollama-a",
                                "config": {"base_url": "http://a"},
                                "models": [{"id": "llama3.2"}],
                            },
                            {
                                "name": "ollama-b",
                                "config": {"base_url": "http://b"},
                                "models": [{"id": "llama3.2"}],
                            },
                        ],
                    }
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    names = {row["name"]: row for row in sdk.models.engine_registry.rows}
    assert report.errors == []
    assert names["ollama-a"]["config"] == {"base_url": "http://a"}
    assert names["ollama-b"]["config"] == {"base_url": "http://b"}
    assert len(report.activated_engines) == 2
    assert [
        call for call in sdk.engines.calls if call[0] == "begin_install"
    ] == [("begin_install", names["ollama-a"]["id"], None)]
    assert [
        call for call in sdk.engines.calls if call[0] == "activate_instance"
    ] == [
        ("activate_instance", names["ollama-a"]["id"]),
        ("activate_instance", names["ollama-b"]["id"]),
    ]


def test_non_configurable_engine_reuses_manifest_registry_row():
    sdk = FakeSDK()
    existing = sdk.models.engine_registry.create(
        {
            "name": "eSpeak",
            "provider": "espeak",
            "config": {},
            "status": "installed",
            "supported": True,
        }
    )

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "espeak",
                        "name": "espeak-local",
                    }
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    assert report.errors == []
    assert len(sdk.models.engine_registry.rows) == 1
    assert sdk.models.engine_registry.rows[0]["id"] == existing["id"]
    assert sdk.models.engine_registry.rows[0]["name"] == "eSpeak"
    assert sdk.models.engine_registry.rows[0]["status"] == "active"
    assert [item["id"] for item in report.activated_engines] == [existing["id"]]


def test_engine_env_cache_is_deleted_before_install(monkeypatch):
    sdk = FakeSDK()
    events = []

    def _clear_engine_env_cache(provider, progress):
        sdk.engines.calls.append(("clear_engine_env_cache", provider))

    monkeypatch.setattr(config_install, "_clear_engine_env_cache", _clear_engine_env_cache)

    report = _run(
        install_engines_from_config(
            sdk,
            {"engines": [{"provider": "espeak"}]},
            reset_mode="keep",
            yes=False,
            progress=events.append,
        )
    )

    assert report.errors == []
    assert sdk.engines.calls.index(("clear_engine_env_cache", "espeak")) < sdk.engines.calls.index(
        ("begin_install", sdk.models.engine_registry.rows[0]["id"], None)
    )


def test_non_configurable_duplicate_cleanup_keeps_canonical_row_and_moves_bindings():
    sdk = FakeSDK()
    canonical = sdk.models.engine_registry.create(
        {
            "name": "eSpeak",
            "provider": "espeak",
            "config": {},
            "status": "installed",
            "supported": True,
        }
    )
    duplicate = sdk.models.engine_registry.create(
        {
            "name": "espeak-local",
            "provider": "espeak",
            "config": {},
            "status": "active",
            "supported": True,
        }
    )
    sdk.models.model_registry.create(
        {
            "name": "duplicate-binding",
            "engine_id": duplicate["id"],
            "status": "active",
        }
    )

    report = _run(
        install_engines_from_config(
            sdk,
            {"engines": [{"provider": "espeak", "name": "espeak-local"}]},
            reset_mode="keep",
            yes=False,
        )
    )

    assert report.errors == []
    assert sdk.models.engine_registry.rows == [
        {
            "id": canonical["id"],
            "name": "eSpeak",
            "provider": "espeak",
            "config": {},
            "status": "active",
            "supported": True,
        }
    ]
    assert sdk.models.model_registry.rows[0]["engine_id"] == canonical["id"]
    assert report.activated_engines[0]["id"] == canonical["id"]


def test_activation_not_ready_is_reported_without_active_count():
    sdk = FakeSDK()

    async def _activate_instance(**kwargs):
        return {
            "activation_ready": False,
            "reason": "missing_dependencies",
            "status": "",
        }

    sdk.engines.activate_instance = _activate_instance

    report = _run(
        install_engines_from_config(
            sdk,
            {"engines": [{"provider": "espeak", "name": "espeak-local"}]},
            reset_mode="keep",
            yes=False,
        )
    )

    assert report.activated_engines == []
    assert report.errors[0]["error"] == "activation_failed:missing_dependencies"


def test_activation_result_must_match_registry_active_status():
    sdk = FakeSDK()

    async def _activate_instance(**kwargs):
        return {"status": "active", "activation_ready": True}

    sdk.engines.activate_instance = _activate_instance

    report = _run(
        install_engines_from_config(
            sdk,
            {"engines": [{"provider": "espeak", "name": "espeak-local"}]},
            reset_mode="keep",
            yes=False,
        )
    )

    assert report.activated_engines == []
    assert report.errors[0]["error"] == "activation_failed:not_active"


def test_catalog_model_download_and_activate(monkeypatch):
    sdk = FakeSDK()
    monkeypatch.setattr(
        config_install,
        "app_ctx",
        lambda: SimpleNamespace(task_manager=FakeTaskManager()),
    )
    monkeypatch.setattr(
        config_install,
        "_static_catalog_entries",
        lambda: [
            {
                "catalog_id": "technical-catalog-id",
                "legacy_model_id": "tiny-local",
                "source_engines": ["llamacpp"],
            }
        ],
    )

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "llamacpp",
                        "name": "llamacpp-local",
                        "models": [{"id": "tiny-local", "download": True}],
                    }
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    assert report.errors == []
    assert report.downloaded_models[0]["model_id"] == "tiny-local"
    assert report.downloaded_models[0]["catalog_model_id"] == "technical-catalog-id"
    assert report.activated_models[0]["model_id"] == "tiny-local"
    binding = sdk.models.model_registry.rows[0]
    available = sdk.models.available_model_registry.rows[0]
    assert binding["available_model_id"] == available["id"]
    assert binding["model_path"] == "models/technical-catalog-id"
    assert binding["is_downloaded"] == 1
    assert binding["extra_config"]["runtime_model_ref"] == "tiny-local"
    assert binding["extra_config"]["defaults"]["generation"] == {"temperature": 0.2}
    assert binding["extra_config"]["defaults"]["runtime"] == {"context_length": 2048}
    assert binding["extra_config"]["features"] == {"tool_calling": {"supported": True}}
    assert binding["extra_config"]["available_model"]["id"] == available["id"]


def test_model_error_does_not_block_next_engine():
    sdk = FakeSDK()

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "openai",
                        "name": "openai-main",
                        "models": [{"id": "missing-model"}],
                    },
                    {
                        "provider": "ollama",
                        "name": "ollama-main",
                        "models": [{"id": "llama3.2"}],
                    },
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    assert len(report.errors) == 1
    assert report.errors[0]["model_id"] == "missing-model"
    assert [item["name"] for item in report.activated_engines] == [
        "openai-main",
        "ollama-main",
    ]
    assert report.activated_models[0]["model_id"] == "llama3.2"


def test_selected_reset_deletes_selected_bindings_and_downloaded_models(monkeypatch):
    sdk = FakeSDK()
    engine = sdk.models.engine_registry.create(
        {
            "name": "llamacpp-local",
            "provider": "llamacpp",
            "config": {},
            "status": "active",
            "supported": True,
        }
    )
    sdk.models.model_registry.create(
        {
            "name": "old-binding",
            "engine_id": engine["id"],
            "available_model_id": 1,
            "status": "active",
        }
    )
    sdk.models.available_model_registry.create(
        {
            "name": "tiny-local",
            "catalog_model_id": "tiny-local",
            "provider_hint": "llamacpp",
            "storage_ref": "models/tiny-local",
        }
    )
    monkeypatch.setattr(
        config_install,
        "app_ctx",
        lambda: SimpleNamespace(task_manager=FakeTaskManager()),
    )
    monkeypatch.setattr(
        config_install,
        "_static_catalog_entries",
        lambda: [
            {
                "catalog_id": "technical-catalog-id",
                "legacy_model_id": "tiny-local",
                "source_engines": ["llamacpp"],
            }
        ],
    )

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "llamacpp",
                        "name": "llamacpp-local",
                        "models": [{"id": "tiny-local", "download": True}],
                    }
                ]
            },
            reset_mode="selected",
            yes=False,
        )
    )

    assert report.errors == []
    assert ("stop_engine", engine["id"]) in sdk.engines.calls
    assert len(sdk.models.model_registry.rows) == 1


def test_selected_reset_matches_non_configurable_provider_manifest_row(monkeypatch):
    sdk = FakeSDK()
    engine = sdk.models.engine_registry.create(
        {
            "name": "eSpeak",
            "provider": "espeak",
            "config": {},
            "status": "active",
            "supported": True,
        }
    )
    sdk.models.model_registry.create(
        {
            "name": "old-binding",
            "engine_id": engine["id"],
            "status": "active",
        }
    )
    cleared = []
    env_exists = {"value": True}

    def _clear_engine_env_cache(provider, progress):
        if env_exists["value"]:
            cleared.append(provider)
            env_exists["value"] = False

    monkeypatch.setattr(config_install, "_clear_engine_env_cache", _clear_engine_env_cache)

    report = _run(
        install_engines_from_config(
            sdk,
            {"engines": [{"provider": "espeak"}]},
            reset_mode="selected",
            yes=False,
        )
    )

    assert report.errors == []
    assert ("stop_engine", engine["id"]) in sdk.engines.calls
    assert len(sdk.models.engine_registry.rows) == 1
    assert sdk.models.engine_registry.rows[0]["id"] == engine["id"]
    assert sdk.models.model_registry.rows == []
    assert cleared == ["espeak"]
    assert ("begin_install", engine["id"], None) in sdk.engines.calls


def test_full_reset_clears_model_state_before_reinstall():
    sdk = FakeSDK()
    engine = sdk.models.engine_registry.create(
        {
            "name": "llamacpp-local",
            "provider": "llamacpp",
            "config": {},
            "status": "active",
            "supported": True,
        }
    )
    sdk.models.model_registry.create(
        {
            "name": "old-binding",
            "engine_id": engine["id"],
            "available_model_id": 1,
            "status": "active",
        }
    )
    sdk.models.available_model_registry.create(
        {
            "name": "tiny-local",
            "catalog_model_id": "tiny-local",
            "provider_hint": "llamacpp",
            "storage_ref": "models/tiny-local",
        }
    )

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "llamacpp",
                        "name": "llamacpp-local",
                    }
                ]
            },
            reset_mode="full",
            yes=True,
        )
    )

    assert report.errors == []
    assert len(sdk.models.model_registry.rows) == 0
    assert len(sdk.models.available_model_registry.rows) == 0
    assert len(sdk.models.engine_registry.rows) == 1
    assert sdk.models.engine_registry.rows[0]["provider"] == "llamacpp"


def test_failed_engine_install_deletes_registry_row():
    sdk = FakeSDK()

    async def _begin_install(**kwargs):
        raise RuntimeError("install_failed")

    sdk.engines.begin_install = _begin_install

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "llamacpp",
                        "name": "llamacpp-local",
                    }
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    assert report.has_errors()
    assert sdk.models.engine_registry.rows == []


def test_failed_engine_install_reports_node_last_error():
    sdk = FakeSDK()

    async def _install_status(**kwargs):
        return {
            "status": "error",
            "nodes": [
                {
                    "node_id": "democr.ai",
                    "status": "error",
                    "last_error": "onnxruntime import failed",
                }
            ],
        }

    sdk.engines.install_status = _install_status

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "onnx",
                        "name": "onnx-local",
                    }
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    assert report.errors[0]["error"] == "install_failed:onnxruntime import failed"
    assert sdk.models.engine_registry.rows == []


def test_artifact_model_download_reports_artifact_upload_required():
    sdk = FakeSDK()
    sdk.engines.catalog["yolo"] = [
        {
            "id": "yolo11n",
            "model_id": "yolo11n",
            "label": "YOLO11n",
            "source_kind": "engine_catalog",
            "capabilities": ["detection"],
            "provisioning": {"mode": "artifact"},
        }
    ]

    report = _run(
        install_engines_from_config(
            sdk,
            {
                "engines": [
                    {
                        "provider": "yolo",
                        "name": "yolo-local",
                        "models": [
                            {
                                "id": "yolo11n",
                                "download": True,
                                "activate": True,
                            }
                        ],
                    }
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    assert report.errors[0]["error"] == "model_requires_artifact_upload:yolo11n"


def test_full_reset_requires_yes():
    sdk = FakeSDK()

    report_error = None
    try:
        _run(
            install_engines_from_config(
                sdk,
                {"engines": [{"provider": "openai", "name": "openai-main"}]},
                reset_mode="full",
                yes=False,
            )
        )
    except Exception as exc:
        report_error = str(exc)

    assert report_error == "full_reset_requires_yes"
