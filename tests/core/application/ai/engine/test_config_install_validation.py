from __future__ import annotations

import pytest

from democrai.core.application.ai.engine.config_install import (
    EngineInstallConfigError,
    _validate_config,
)


@pytest.mark.parametrize(
    "config,error",
    [
        ([], "config_must_be_mapping"),
        ({}, "engines_must_be_non_empty_list"),
        ({"engines": []}, "engines_must_be_non_empty_list"),
        ({"engines": [{}]}, "engines[0].provider_required"),
        (
            {"engines": [{"provider": "openai", "config": {}, "instances": []}]},
            "engines[0].config_cannot_be_used_with_instances",
        ),
        (
            {"engines": [{"provider": "openai", "instances": {}}]},
            "engines[0].instances_must_be_list",
        ),
        (
            {"engines": [{"provider": "openai", "models": [{}]}]},
            "engines[0].models[0].id_required",
        ),
        (
            {
                "engines": [
                    {
                        "provider": "openai",
                        "models": [{"id": "x", "catalog_model_id": "x"}],
                    }
                ]
            },
            "engines[0].models[0].catalog_model_id_not_allowed",
        ),
    ],
)
def test_validate_config_errors(config, error):
    with pytest.raises(EngineInstallConfigError) as exc:
        _validate_config(config)

    assert str(exc.value) == error


def test_validate_config_missing_env_var(monkeypatch):
    monkeypatch.delenv("DEM_OCRAI_MISSING", raising=False)

    with pytest.raises(EngineInstallConfigError) as exc:
        _validate_config(
            {
                "engines": [
                    {
                        "provider": "openai",
                        "config": {"api_key": "${DEM_OCRAI_MISSING}"},
                    }
                ]
            }
        )

    assert str(exc.value) == "engines[0].config.api_key_env_missing:DEM_OCRAI_MISSING"


def test_validate_config_expands_instances(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")

    specs = _validate_config(
        {
            "engines": [
                {
                    "provider": "openai",
                    "instances": [
                        {
                            "name": "openai-main",
                            "config": {"api_key": "${OPENAI_API_KEY}"},
                            "models": [{"id": "gpt-5.2"}],
                        }
                    ],
                }
            ]
        }
    )

    assert len(specs) == 1
    assert specs[0].provider == "openai"
    assert specs[0].name == "openai-main"
    assert specs[0].config == {"api_key": "secret"}
    assert specs[0].models[0].id == "gpt-5.2"
    assert specs[0].models[0].download is False
    assert specs[0].models[0].activate is True
