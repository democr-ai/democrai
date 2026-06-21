from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def test_qwen_tts_engine_does_not_import_core_directly():
    import engines.qwen_tts.engine as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")

    assert "from democrai.core" not in source
    assert "import democrai.core" not in source


def test_qwen_tts_tokenizer_download_uses_filesystem_local_dir(monkeypatch, tmp_path):
    import engines.qwen_tts.engine as mod

    captured = {}

    def snapshot_download(**kwargs):
        captured["kwargs"] = kwargs
        return kwargs["local_dir"]

    fake_hub = SimpleNamespace(snapshot_download=snapshot_download)

    monkeypatch.setattr(mod, "get_engine_local_cache_path", lambda _id=None: tmp_path / "cache")
    monkeypatch.setattr(mod, "fs_path", lambda path: f"FS::{path}")
    monkeypatch.setattr(mod, "logical_path", lambda path: str(path).removeprefix("FS::"))
    monkeypatch.setattr(mod.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(mod.importlib, "import_module", lambda name: fake_hub if name == "huggingface_hub" else None)
    monkeypatch.setattr(mod.QwenTTSEngine, "_configured_tokenizer_path", classmethod(lambda cls: ""))

    result = mod.QwenTTSEngine._install_tokenizer(force=True)

    expected = tmp_path / "cache" / "tokenizer"
    assert captured["kwargs"]["local_dir"] == f"FS::{expected}"
    assert captured["kwargs"]["repo_id"] == mod.TOKENIZER_REPO
    assert "local_dir_use_symlinks" not in captured["kwargs"]
    assert result == str(expected)


def test_qwen_tts_configured_tokenizer_path_accepts_downloaded_files(monkeypatch, tmp_path):
    import engines.qwen_tts.engine as mod

    tokenizer_path = tmp_path / "cache" / "tokenizer"
    tokenizer_path.mkdir(parents=True)
    for filename in mod.QwenTTSEngine._tokenizer_required_files():
        (tokenizer_path / filename).write_text("ok", encoding="utf-8")

    monkeypatch.setattr(mod, "get_engine_local_cache_path", lambda _id=None: tmp_path / "cache")

    assert mod.QwenTTSEngine._configured_tokenizer_path() == str(tokenizer_path)


def test_qwen_tts_configured_tokenizer_path_rejects_incomplete_download(monkeypatch, tmp_path):
    import engines.qwen_tts.engine as mod

    tokenizer_path = tmp_path / "cache" / "tokenizer"
    tokenizer_path.mkdir(parents=True)
    (tokenizer_path / "config.json").write_text("ok", encoding="utf-8")
    (tokenizer_path / "model.safetensors").write_text("ok", encoding="utf-8")

    monkeypatch.setattr(mod, "get_engine_local_cache_path", lambda _id=None: tmp_path / "cache")

    assert mod.QwenTTSEngine._configured_tokenizer_path() == ""
