from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.system.actions.engine.available_models import activation as activation_mod
from modules.system.actions.engine.available_models.helpers import _defaults_from_payload
from modules.system.utils.ui.model.configuration_form import model_configuration_form_model


def test_embedding_activation_form_adds_embedding_policy_fields():
    sdk = SimpleNamespace(i18n=SimpleNamespace(t=lambda key, **_kwargs: key))

    fields = model_configuration_form_model(
        sdk,
        {
            "model_capabilities": ["embedding"],
            "model_configuration_form_schema": {
                "capabilities": {
                    "name": "capabilities",
                    "type": "tags",
                    "item_schema": {
                        "type": "select",
                        "options_key": "model_capabilities",
                    },
                },
                "features": [
                    {
                        "capability": "embedding",
                        "schema_field": "dim",
                        "name": "embedding_dim",
                    },
                    {
                        "capability": "embedding",
                        "schema_field": "document_prefix",
                        "name": "embedding_document_prefix",
                    },
                    {
                        "capability": "embedding",
                        "schema_field": "query_prefix",
                        "name": "embedding_query_prefix",
                    },
                    {
                        "capability": "embedding",
                        "schema_field": "default_purpose",
                        "name": "embedding_default_purpose",
                    },
                ],
            },
            "model_feature_schemas": {
                "embedding": {
                    "fields": [
                        {"name": "dim", "type": "number", "default": 384},
                        {"name": "document_prefix", "type": "text", "default": ""},
                        {"name": "query_prefix", "type": "text", "default": ""},
                        {
                            "name": "default_purpose",
                            "type": "select",
                            "default": "document",
                            "options": [
                                {"label": "document", "value": "document"},
                                {"label": "query", "value": "query"},
                            ],
                        },
                    ]
                }
            },
        },
        capabilities=["embedding"],
        extra_config={
            "defaults": {
                "runtime": {
                    "embedding_input_policy": {
                        "document_prefix": "search_document: ",
                        "query_prefix": "search_query: ",
                        "default_purpose": "document",
                    }
                }
            }
        },
    )

    by_name = {field["name"]: field for field in fields}
    assert by_name["embedding_document_prefix"]["value"] == "search_document: "
    assert by_name["embedding_query_prefix"]["value"] == "search_query: "
    assert by_name["embedding_default_purpose"]["value"] == "document"


def test_embedding_policy_payload_is_saved_in_runtime_defaults():
    defaults = _defaults_from_payload(
        {
            "embedding_document_prefix": "search_document: ",
            "embedding_query_prefix": "search_query: ",
            "embedding_default_purpose": "query",
        }
    )

    assert defaults["runtime"]["embedding_input_policy"] == {
        "document_prefix": "search_document: ",
        "query_prefix": "search_query: ",
        "default_purpose": "query",
    }


def test_optional_runtime_numbers_are_not_saved_when_empty():
    defaults = _defaults_from_payload(
        {
            "top_k": "",
            "max_tokens_per_doc": "",
        },
        runtime_field_names=["top_k", "max_tokens_per_doc"],
        runtime_options_schema={
            "fields": [
                {
                    "name": "top_k",
                    "type": "integer",
                    "default": None,
                    "min": 1,
                    "step": 1,
                },
                {
                    "name": "max_tokens_per_doc",
                    "type": "number",
                    "default": None,
                    "min": 1,
                    "step": 1,
                },
            ]
        },
    )

    assert defaults["runtime"] == {}


def test_gliner_glirel_runtime_numbers_are_not_saved_when_empty():
    defaults = _defaults_from_payload(
        {
            "max_relation_tokens": "",
            "relation_window_overlap": "",
        },
        runtime_field_names=["max_relation_tokens", "relation_window_overlap"],
        runtime_options_schema={
            "fields": [
                {
                    "name": "max_relation_tokens",
                    "type": "integer",
                    "default": 360,
                    "min": 1,
                },
                {
                    "name": "relation_window_overlap",
                    "type": "integer",
                    "default": 48,
                    "min": 0,
                },
            ]
        },
    )

    assert defaults["runtime"] == {}


def test_gliner_glirel_runtime_numbers_are_saved_when_valid():
    defaults = _defaults_from_payload(
        {
            "max_relation_tokens": "512",
            "relation_window_overlap": "64",
        },
        runtime_field_names=["max_relation_tokens", "relation_window_overlap"],
        runtime_options_schema={
            "fields": [
                {
                    "name": "max_relation_tokens",
                    "type": "integer",
                    "default": 360,
                    "min": 1,
                },
                {
                    "name": "relation_window_overlap",
                    "type": "integer",
                    "default": 48,
                    "min": 0,
                },
            ]
        },
    )

    assert defaults["runtime"] == {
        "max_relation_tokens": 512,
        "relation_window_overlap": 64,
    }


@pytest.mark.asyncio
async def test_gliner_glirel_available_model_activation_keeps_catalog_defaults_for_empty_numbers():
    created_payloads = []

    class EngineRegistry:
        @staticmethod
        def view(row_id):
            assert row_id == 9
            return {"id": 9, "provider": "gliner_glirel"}

    class AvailableModelRegistry:
        @staticmethod
        def view(row_id):
            assert row_id == 15
            return {
                "id": 15,
                "name": "gliner-medium-glirel-large",
                "label": "GLiNER Medium + GLiREL Large",
                "provider_hint": "gliner_glirel",
                "format": "engine_catalog",
                "source_kind": "engine_catalog",
                "capabilities": ["triples_extractor"],
                "extra_config": {
                    "defaults": {
                        "runtime": {
                            "max_relation_tokens": 360,
                            "relation_window_overlap": 48,
                        }
                    },
                    "options_schema": {
                        "fields": [
                            {
                                "name": "max_relation_tokens",
                                "type": "integer",
                                "min": 1,
                                "default": 360,
                            },
                            {
                                "name": "relation_window_overlap",
                                "type": "integer",
                                "min": 0,
                                "default": 48,
                            },
                        ]
                    },
                },
            }

    class ModelRegistry:
        @staticmethod
        def all(filters):
            assert filters == {"engine_id": 9, "available_model_id": 15}
            return {"rows": []}

        @staticmethod
        def create(payload):
            created_payloads.append(payload)
            return {**payload, "id": 77}

    class Engines:
        @staticmethod
        async def constants():
            return {
                "model_capabilities": ["triples_extractor"],
                "model_feature_schemas": {},
            }

    class Effects:
        @staticmethod
        def notify(channel, payload):
            return {"notify": {"channel": channel, "payload": payload}}

        @staticmethod
        def ui_messages(messages):
            return {"ui_messages": messages}

        @staticmethod
        def render():
            return {"render": True}

        @staticmethod
        def respond(*effects):
            return {"effects": effects}

    module_sdk = SimpleNamespace(
        engines=Engines(),
        models=SimpleNamespace(
            engine_registry=EngineRegistry(),
            available_model_registry=AvailableModelRegistry(),
            model_registry=ModelRegistry(),
        ),
        effects=Effects(),
        i18n=SimpleNamespace(t=lambda key, **_kwargs: key),
    )

    result = await activation_mod.activate_available_model_for_engine(
        {
            "engine_id": 9,
            "available_model_id": 15,
            "model_id": "gliner-medium-glirel-large",
            "items": [
                {
                    "id": "gliner-medium-glirel-large",
                    "model_id": "gliner-medium-glirel-large",
                    "capabilities": ["triples_extractor"],
                    "search_text": "gliner glirel triples",
                }
            ],
            "engine_models_available_name_filter": "",
            "engine_models_available_capability_filter": "",
            "form_id": "form",
            "form": {
                "capabilities": ["triples_extractor"],
                "max_relation_tokens": "",
                "relation_window_overlap": "",
            },
        },
        {},
        module_sdk,
    )

    assert result["effects"][1]["notify"]["payload"]["level"] == "success"
    runtime_defaults = created_payloads[0]["extra_config"]["defaults"]["runtime"]
    assert runtime_defaults["max_relation_tokens"] == 360
    assert runtime_defaults["relation_window_overlap"] == 48


def test_model_configuration_form_adds_reasoning_capability_option_fields():
    sdk = SimpleNamespace(i18n=SimpleNamespace(t=lambda key, **_kwargs: key))

    fields = model_configuration_form_model(
        sdk,
        {
            "model_capabilities": ["chat", "reasoning"],
            "model_configuration_form_schema": {
                "capabilities": {
                    "name": "capabilities",
                    "type": "tags",
                    "item_schema": {
                        "type": "select",
                        "options_key": "model_capabilities",
                    },
                },
                "features": [],
            },
            "model_feature_schemas": {},
        },
        capabilities=["chat", "reasoning"],
        extra_config={
            "defaults": {
                "generation": {
                    "extra": {
                        "reasoning_budget": 2048,
                    }
                }
            }
        },
        capability_option_fields={
            "reasoning": [
                {
                    "name": "reasoning_budget",
                    "label": "Reasoning budget",
                    "type": "number",
                    "default": 4096,
                }
            ]
        },
    )

    by_name = {field["name"]: field for field in fields}
    field = by_name["extra.reasoning_budget"]
    assert field["value"] == 2048
    assert field["show_if"]["conditions"][0]["right"] == "reasoning"
