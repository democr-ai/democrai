from __future__ import annotations

from types import SimpleNamespace

import democrai.core.application.services.media_uploads as media_uploads_mod
import democrai.sdk.database as database_mod
import democrai.sdk.effects as effects_mod
import democrai.sdk.media as media_mod
import democrai.sdk.models as models_mod
import democrai.sdk.ui as sdk_ui_mod
from democrai.core.runtime.foundation.app import request_context_scope
from democrai.core.platform.ui.yaml_builder import YamlUIBuilder


def test_docs_example_effects_respond_and_property_update_payload():
    sdk = SimpleNamespace(module_name="demo", ui=sdk_ui_mod)
    effects = effects_mod.Effects(sdk)

    response = effects.respond(
        effects.notify(
            "toast",
            {"title": "Saved", "text": "Changes applied", "variant": "success"},
        ),
        effects.ui_property_update(
            "status_text",
            "text",
            {"literalString": "Done"},
        ),
        effects.navigate("/demo/anonim/index", render=True),
    )

    assert list(response) == ["effects"]
    assert len(response["effects"]) == 3
    assert response["effects"][0]["type"] == "notify"
    assert response["effects"][1]["propertyUpdate"] == {
        "surfaceId": "main",
        "componentId": "status_text",
        "propertyName": "text",
        "action": "set",
        "value": {"literalString": "Done"},
    }
    assert response["effects"][2] == {
        "type": "navigate",
        "path": "/demo/anonim/index",
        "render": True,
    }


def test_docs_example_yaml_ui_builds_nested_surface_payload():
    yaml_content = """
- kind: Column
  id: tickets_root
  spacing: 12
  children:
    - kind: Title
      id: tickets_title
      text: "Tickets"
    - kind: DataTable
      id: tickets_table
      model: []
      rows: []
    - kind: Form
      id: ticket_form
      submit_label: "Create Ticket"
      action: "tickets.create_ticket"
      params:
        table_id: tickets_table
      model:
        - type: text
          name: title
          label: "Title"
          required: true
"""
    builder = YamlUIBuilder().build(yaml_content)

    payload = builder.build_surface_update_payload("main")
    assert len(payload) == 1

    components = payload[0]["surfaceUpdate"]["components"]
    root = next(component for component in components if component["id"] == "tickets_root")
    assert root["component"]["Column"]["spacing"] == 12

    children = root["children"]["explicitList"]
    assert [child["id"] for child in children] == [
        "tickets_title",
        "tickets_table",
        "ticket_form",
    ]
    assert children[0]["component"]["Title"]["text"] == {"literalString": "Tickets"}
    assert children[1]["component"]["DataTable"]["rows"] == []
    assert children[2]["component"]["Form"]["submit_label"] == "Create Ticket"
    assert children[2]["component"]["Form"]["action"] == {
        "name": "tickets.create_ticket",
        "context": {"table_id": "tickets_table"},
    }


def test_docs_example_core_models_proxy_uses_session_scope(monkeypatch):
    captured = {}

    class _ResolvedModel:
        def list(self, *, page, page_size, filters, sort):
            captured["page"] = page
            captured["page_size"] = page_size
            captured["filters"] = filters
            captured["sort"] = sort
            return {"rows": [], "page": page, "page_size": page_size, "total_rows": 0}

    def _build_core_model(name, ctx):
        captured["model_name"] = name
        captured["ctx"] = ctx
        return _ResolvedModel()

    monkeypatch.setattr(models_mod, "build_core_model", _build_core_model)

    sdk = SimpleNamespace(
        module_name="tickets",
        session={
            "user": {
                "id": 7,
                "organization_id": 42,
                "access_level": 2,
            }
        },
    )
    models = models_mod.CoreModelsSDK(sdk)

    result = models.users.list(page=0, page_size=25, filters={"active": True})

    assert captured["model_name"] == "users"
    assert captured["ctx"].user_id == 7
    assert captured["ctx"].organization_id == 42
    assert captured["ctx"].access_level == 2
    assert captured["ctx"].module_name == "tickets"
    assert result["page_size"] == 25


def test_docs_example_module_database_add_auto_assigns_scope(monkeypatch):
    captured = {}

    class _FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def add(self, obj):
            captured["added"] = obj

        def commit(self):
            captured["committed"] = True

        def refresh(self, obj):
            captured["refreshed"] = obj

    monkeypatch.setattr(database_mod.DataStore, "_get_session", lambda self: _FakeSession())
    monkeypatch.setattr(database_mod.DataStore, "_attach_actor", lambda self, session: None)

    Base = database_mod.get_module_base("tickets")

    class Ticket(Base):
        __abstract__ = True

        def __init__(self, title: str):
            self.title = title

    store = database_mod.ModuleDataStore(
        user_id=12,
        organization_id=99,
        access_level=2,
        module_name="tickets",
    )
    ticket = Ticket(title="Broken login")

    saved = store.add(ticket)

    assert saved is ticket
    assert ticket.user_id == 12
    assert ticket.organization_id == 99
    assert captured["added"] is ticket
    assert captured["committed"] is True


def test_docs_example_media_add_uses_sdk_session_scope(monkeypatch):
    calls = []

    monkeypatch.setattr(
        media_mod,
        "detect_mime_type",
        lambda **kwargs: SimpleNamespace(mime_type="application/pdf", source="filename"),
    )
    monkeypatch.setattr(
        media_mod,
        "store_uploaded_media",
        lambda **kwargs: calls.append(kwargs)
        or media_uploads_mod.MediaUploadResult(
            file_id="f1",
            storage_path="media/demo/uid_8/f1_doc.pdf",
            stored_filename="f1_doc.pdf",
            sha256="sha",
            size_bytes=3,
            scope_type="organization",
        ),
    )

    sdk = SimpleNamespace(
        module_name="demo",
        session={"user": {"id": 8, "organization_id": 5, "access_level": 2}},
        module_path="/tmp/demo",
    )
    media = media_mod.Media(sdk)

    with request_context_scope(
        {
            "request_id": "docs-media-add",
            "user": 8,
            "organization_id": 5,
            "access_level": 2,
            "module_name": "demo",
        }
    ):
        result = media.add("doc.pdf", b"abc")

    assert result == "media/demo/uid_8/f1_doc.pdf"
    assert calls == [
        {
            "module_name": "demo",
            "original_filename": "doc.pdf",
            "payload": b"abc",
            "content_type": "application/pdf",
            "user_id": 8,
            "organization_id": 5,
            "access_level": 2,
            "uploaded_by": 8,
        }
    ]
