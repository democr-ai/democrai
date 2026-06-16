from __future__ import annotations

from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.orchestrator.executor import (
    _materialize_storage_refs,
)
from democrai.core.runtime.foundation.app import app_ctx


def _with_media(loader):
    ctx = app_ctx()
    previous = getattr(ctx, "media", None)
    ctx.media = loader
    return ctx, previous


def test_media_storage_path_materialized_for_transcribe():
    ctx, previous = _with_media(
        SimpleNamespace(load=lambda path: b"RIFFdata" if path == "media/a.wav" else b"")
    )
    try:
        payload = _materialize_storage_refs(
            {"media_storage_path": "media/a.wav", "language": "it"},
            method="transcribe",
        )
    finally:
        ctx.media = previous
    assert payload == {"audio_data": b"RIFFdata", "language": "it"}


def test_media_ref_conflicts_with_inline_payload_fails():
    ctx, previous = _with_media(SimpleNamespace(load=lambda path: b"from-storage"))
    try:
        with pytest.raises(
            RuntimeError,
            match="engine_orchestrator_media_ref_payload_conflict:transcribe",
        ):
            _materialize_storage_refs(
                {"media_storage_path": "media/a.wav", "audio_data": b"inline"},
                method="transcribe",
            )
    finally:
        ctx.media = previous


def test_unsupported_method_fails_explicitly():
    with pytest.raises(RuntimeError, match="media_ref_unsupported_method:generate_completion"):
        _materialize_storage_refs(
            {"media_storage_path": "media/a.wav"},
            method="generate_completion",
        )


def test_missing_media_provider_fails_explicitly():
    ctx, previous = _with_media(None)
    try:
        with pytest.raises(RuntimeError, match="media_provider_unavailable"):
            _materialize_storage_refs(
                {"media_storage_path": "media/a.wav"}, method="transcribe"
            )
    finally:
        ctx.media = previous


def test_payload_without_refs_untouched():
    payload = {"messages": [], "options": {"x": 1}}
    assert (
        _materialize_storage_refs(dict(payload), method="generate_completion")
        == payload
    )
