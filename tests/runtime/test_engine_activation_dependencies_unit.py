from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import democrai.core.application.ai.engine.requirements as requirements_mod
import democrai.core.application.ai.engine.runtime as engine_runtime_mod
from democrai.core.infrastructure.database.models import Base, EngineRegistry
from modules.system.utils.actions.engine.config import upsert_engine_from_config


def test_gemini_ready_checks_google_genai_module(monkeypatch):
    import democrai.core.application.ai.engine.base.engine as base_engine_mod
    import engines.gemini.engine as gemini_mod

    checked = []

    def fake_find_spec(module_name):
        checked.append(module_name)
        if module_name == "google":
            return object()
        return None

    monkeypatch.setattr(base_engine_mod.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(gemini_mod, "_google_genai_version_matches", lambda: True)
    monkeypatch.setattr(
        gemini_mod,
        "_google_genai_runtime_symbols_available",
        lambda: True,
    )

    result = gemini_mod.GeminiEngine._check_ready()

    assert "google.genai" in checked
    assert "google" not in checked
    assert result["ready"] is False
    assert result["missing_local"] == ["google-genai==2.7.0"]


@pytest.mark.asyncio
async def test_remote_activation_requires_declared_dependencies(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(requirements_mod, "SessionLocal", SessionLocal)

    with SessionLocal() as session:
        row = EngineRegistry(
            name="gemini-main",
            provider="gemini",
            config={"api_key": "secret"},
            status="uninstalled",
            supported=True,
        )
        session.add(row)
        session.commit()
        engine_registry_id = row.id

    monkeypatch.setattr(
        requirements_mod,
        "provider_requirements",
        lambda provider_id: {
            "provider": provider_id,
            "provider_label": "Gemini",
            "supported": True,
            "configurable": True,
            "remote": True,
            "requires_config": True,
            "config_schema": [
                {
                    "name": "api_key",
                    "validations": [{"rule": "required"}],
                }
            ],
            "missing_dependencies": [
                {
                    "dependency_key": "google_genai",
                    "module": "google.genai",
                    "label": "google-genai",
                }
            ],
        },
    )
    monkeypatch.setattr(
        engine_runtime_mod,
        "check_engine_ready_runtime",
        lambda *, engine_id: {
            "ready": False,
            "missing_shared": [],
            "missing_local": ["google-genai"],
            "message": "Gemini engine requires shared state or local dependencies",
        },
    )

    result = await requirements_mod.activation_requirements(
        engine_registry_id=engine_registry_id,
    )

    assert result["ready"] is False
    assert result["reason"] == "missing_dependencies"
    assert result["missing_dependencies"][0]["dependency_key"] == "google-genai"


def test_configurable_remote_engine_created_uninstalled(monkeypatch):
    created_payloads = []

    class EngineRegistryModel:
        @staticmethod
        def create(payload):
            created_payloads.append(payload)
            return {"id": 42}

    module_sdk = SimpleNamespace(
        models=SimpleNamespace(engine_registry=EngineRegistryModel()),
    )
    monkeypatch.setattr(
        "modules.system.utils.actions.engine.config.provider_requirements",
        lambda provider_id: {
            "provider": provider_id,
            "supported": True,
            "remote": True,
            "configurable": True,
        },
    )

    engine_id = upsert_engine_from_config(
        module_sdk,
        provider="gemini",
        engine_id=None,
        payload={"name": "gemini-main", "api_key": "secret"},
    )

    assert engine_id == 42
    assert created_payloads[0]["status"] == "uninstalled"
