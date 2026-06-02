from __future__ import annotations

from modules.system.actions.engine.model_catalog import _feature_config


def test_catalog_feature_config_uses_runtime_schema():
    config = _feature_config(
        {
            "feature__embedding__mime_types": ["text/plain"],
        },
        "embedding",
        {
            "default": {"dim": 384},
            "fields": [
                {
                    "name": "mime_types",
                    "item_schema": {
                        "options": [
                            {"label": "Text", "value": "text/plain"},
                        ]
                    },
                }
            ],
        },
    )

    assert config == {
        "dim": 384,
        "supported": True,
        "mime_types": ["text/plain"],
    }
