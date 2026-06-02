from __future__ import annotations

from types import SimpleNamespace

import clients.qtdesktop.ui.renderers.domains.forms.attachment as mod


def test_infer_module_name_from_action_store_and_fallback():
    assert (
        mod._infer_module_name(
            {"action": {"name": "system.activate_available_model_for_engine"}},
            app_instance=SimpleNamespace(),
        )
        == "system"
    )

    store = SimpleNamespace(get=lambda _k, _d=None, _s=None: "/chat/index")
    assert mod._infer_module_name({}, app_instance=SimpleNamespace(store=store)) == "chat"

    assert mod._infer_module_name({}, app_instance=SimpleNamespace()) == "core"


def test_upload_file_to_media_storage_success(monkeypatch, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")

    calls: dict[str, object] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return (
                b'{"status":"ok","file_id":"fid-1","storage_path":"media/chat/u/doc.txt",'
                b'"size_bytes":5,"content_type":"text/plain"}'
            )

    def _urlopen(request, timeout=30.0):  # noqa: ARG001
        calls["request"] = request
        return _Response()

    monkeypatch.setattr(mod.urllib.request, "urlopen", _urlopen)
    app = SimpleNamespace(host="127.0.0.1", port=8000, jwt="token-1")
    out = mod._upload_file_to_media_storage(
        local_path=str(f),
        module_name="chat",
        ingest=False,
        app_instance=app,
    )
    assert out is not None
    assert out["path"] == "media/chat/u/doc.txt"
    assert "source_path" not in out
    assert out["file_id"] == "fid-1"
    assert out["content_type"] == "text/plain"
    assert out["size_bytes"] == 5

    request = calls["request"]
    assert request is not None
    assert b'name="module_name"' in request.data
    assert b"chat" in request.data
    assert b'name="file"; filename="doc.txt"' in request.data


def test_upload_file_to_media_storage_requires_jwt(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("hello", encoding="utf-8")
    out = mod._upload_file_to_media_storage(
        local_path=str(f),
        module_name="chat",
        ingest=False,
        app_instance=SimpleNamespace(host="127.0.0.1", port=8000, jwt=""),
    )
    assert out is None
