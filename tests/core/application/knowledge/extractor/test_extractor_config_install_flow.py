from __future__ import annotations

import asyncio

from democrai.core.application.knowledge.extractor import config_install
from democrai.core.application.knowledge.extractor.config_install import (
    install_extractors_from_config,
)


class FakeModelProxy:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.next_id = 1 + max([int(row.get("id") or 0) for row in self.rows] or [0])

    def all(self):
        return [dict(row) for row in self.rows]

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

    def delete(self, entity_id):
        self.rows = [row for row in self.rows if int(row["id"]) != int(entity_id)]
        return True

    def list(self, *, page=0, page_size=20, filters=None, sort=None):
        filters = filters or {}
        rows = []
        for row in self.rows:
            matched = True
            for key, value in filters.items():
                if str(row.get(key) or "") != str(value):
                    matched = False
                    break
            if matched:
                rows.append(dict(row))
        return {"rows": rows, "items": rows}


class FakeModels:
    def __init__(self):
        self.extractor_registry = FakeModelProxy()
        self.extractor_mime_type_binding = FakeModelProxy()
        self.extractor_node_install_registry = FakeModelProxy()


class FakeExtractors:
    def __init__(self, models):
        self.models = models
        self.calls = []

    async def request_install(
        self,
        *,
        extractor_id,
        force=False,
        install_config=None,
        requested_by=None,
        task_id=None,
    ):
        self.calls.append(("request_install", extractor_id, dict(install_config or {})))
        event_id = f"event-{extractor_id}"
        self.models.extractor_node_install_registry.create(
            {
                "extractor_id": extractor_id,
                "status": "installed",
                "last_event_id": event_id,
                "last_error": "",
            }
        )
        return {"event_id": event_id}

    async def sync_runtime(self):
        self.calls.append(("sync_runtime",))

    def set_mime_type_binding(self, *, mime_type, extractor_id):
        self.calls.append(("set_mime_type_binding", mime_type, extractor_id))
        existing = None
        for row in self.models.extractor_mime_type_binding.rows:
            if row["mime_type"] == mime_type:
                existing = row
                break
        if existing is not None:
            return self.models.extractor_mime_type_binding.update(
                existing["id"],
                {"extractor_id": extractor_id},
            )
        return self.models.extractor_mime_type_binding.create(
            {"mime_type": mime_type, "extractor_id": extractor_id}
        )


class FakeSDK:
    def __init__(self):
        self.models = FakeModels()
        self.extractors = FakeExtractors(self.models)


def _run(coro):
    return asyncio.run(coro)


def _manifest(extractor_id: str):
    return {
        "id": extractor_id,
        "name": extractor_id.title(),
        "file_extensions": [".txt"],
        "mime_types": ["text/plain", "application/pdf", "audio/mpeg"],
    }


def test_install_activate_and_bind_mime(monkeypatch):
    monkeypatch.setattr(config_install, "get_extractor_manifest", _manifest)
    sdk = FakeSDK()

    report = _run(
        install_extractors_from_config(
            sdk,
            {
                "extractors": [
                    {
                        "id": "docling",
                        "install_config": {"ocr_engine": "rapidocr"},
                        "runtime_config": {"chunk_size": 1200},
                        "mime_bindings": ["application/pdf", "text/plain"],
                    }
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    row = sdk.models.extractor_registry.rows[0]
    assert report.errors == []
    assert row["extractor_id"] == "docling"
    assert row["install_config"] == {"ocr_engine": "rapidocr"}
    assert row["config"] == {"chunk_size": 1200}
    assert row["status"] == "active"
    assert report.installed[0]["extractor_id"] == "docling"
    assert report.activated[0]["extractor_id"] == "docling"
    assert len(report.mime_bindings) == 2
    assert ("sync_runtime",) in sdk.extractors.calls


def test_extractor_error_does_not_block_next(monkeypatch):
    def manifest(extractor_id: str):
        if extractor_id == "missing":
            return None
        return _manifest(extractor_id)

    monkeypatch.setattr(config_install, "get_extractor_manifest", manifest)
    sdk = FakeSDK()

    report = _run(
        install_extractors_from_config(
            sdk,
            {
                "extractors": [
                    {"id": "missing"},
                    {"id": "docling", "mime_bindings": ["text/plain"]},
                ]
            },
            reset_mode="keep",
            yes=False,
        )
    )

    assert len(report.errors) == 1
    assert report.errors[0]["extractor_id"] == "missing"
    assert report.activated[0]["extractor_id"] == "docling"


def test_selected_reset_only_selected(monkeypatch, tmp_path):
    monkeypatch.setattr(config_install, "get_extractor_manifest", _manifest)
    selected_root = tmp_path / "docling"
    selected_root.mkdir()
    monkeypatch.setattr(
        config_install,
        "get_extractor_local_env_path",
        lambda extractor_id: selected_root,
    )
    sdk = FakeSDK()
    selected = sdk.models.extractor_registry.create(
        {"name": "Docling", "extractor_id": "docling", "status": "active"}
    )
    other = sdk.models.extractor_registry.create(
        {"name": "Audio", "extractor_id": "ai_audio", "status": "active"}
    )
    sdk.models.extractor_mime_type_binding.create(
        {"mime_type": "text/plain", "extractor_id": "docling"}
    )
    sdk.models.extractor_mime_type_binding.create(
        {"mime_type": "audio/mpeg", "extractor_id": "ai_audio"}
    )

    report = _run(
        install_extractors_from_config(
            sdk,
            {"extractors": [{"id": "docling"}]},
            reset_mode="selected",
            yes=False,
        )
    )

    remaining_rows = {row["extractor_id"]: row for row in sdk.models.extractor_registry.rows}
    remaining_bindings = {
        row["extractor_id"] for row in sdk.models.extractor_mime_type_binding.rows
    }
    assert report.errors == []
    assert remaining_rows["docling"]["id"] != selected["id"]
    assert remaining_rows["ai_audio"]["id"] == other["id"]
    assert "docling" not in remaining_bindings
    assert "ai_audio" in remaining_bindings
    assert not selected_root.exists()
