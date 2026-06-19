from __future__ import annotations

import pytest

from democrai.core.application.knowledge.extractor import config_install
from democrai.core.application.knowledge.extractor.config_install import (
    ExtractorInstallConfigError,
    _validate_config,
)


def _manifest(extractor_id: str):
    return {
        "id": extractor_id,
        "name": extractor_id.title(),
        "file_extensions": [".txt"],
        "mime_types": ["text/plain", "application/pdf", "audio/mpeg"],
    }


@pytest.fixture(autouse=True)
def patch_manifest(monkeypatch):
    monkeypatch.setattr(config_install, "get_extractor_manifest", _manifest)


@pytest.mark.parametrize(
    "config,error",
    [
        ([], "config_must_be_mapping"),
        ({}, "extractors_must_be_non_empty_list"),
        ({"extractors": []}, "extractors_must_be_non_empty_list"),
        ({"extractors": [{}]}, "extractors[0].id_required"),
        (
            {"extractors": [{"id": "docling"}, {"id": "docling"}]},
            "extractors[1].duplicate_id:docling",
        ),
        (
            {"extractors": [{"id": "docling", "mime_bindings": ["image/png"]}]},
            "extractors[0].mime_bindings.unsupported:docling:image/png",
        ),
    ],
)
def test_validate_config_errors(config, error):
    with pytest.raises(ExtractorInstallConfigError) as exc:
        _validate_config(config)

    assert str(exc.value) == error


def test_validate_config_missing_env_var(monkeypatch):
    monkeypatch.delenv("MISSING_EXTRACTOR_MODEL", raising=False)

    with pytest.raises(ExtractorInstallConfigError) as exc:
        _validate_config(
            {
                "extractors": [
                    {
                        "id": "ai_audio",
                        "runtime_config": {
                            "model_registry_id": "${MISSING_EXTRACTOR_MODEL}"
                        },
                    }
                ]
            }
        )

    assert (
        str(exc.value)
        == "extractors[0].runtime_config.model_registry_id_env_missing:MISSING_EXTRACTOR_MODEL"
    )


def test_validate_config_expands_valid_spec(monkeypatch):
    monkeypatch.setenv("AUDIO_MODEL_REGISTRY_ID", "12")

    specs = _validate_config(
        {
            "extractors": [
                {
                    "id": "ai_audio",
                    "name": "audio-main",
                    "runtime_config": {
                        "model_registry_id": "${AUDIO_MODEL_REGISTRY_ID}"
                    },
                    "mime_bindings": ["audio/mpeg"],
                }
            ]
        }
    )

    assert len(specs) == 1
    assert specs[0].id == "ai_audio"
    assert specs[0].name == "audio-main"
    assert specs[0].runtime_config == {"model_registry_id": "12"}
    assert specs[0].mime_bindings == ["audio/mpeg"]
