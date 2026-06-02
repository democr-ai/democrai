from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.system.actions.engine.model_tests.common import get_provider, load_context
from modules.system.utils.actions.engine.model_test_support import (
    _number_value,
    _optional_int_value,
    _runtime_schema_value,
)


def test_number_value_uses_default_only_for_empty_values():
    assert _number_value(None, 0.7) == 0.7
    assert _number_value("", 0.7) == 0.7
    assert _number_value("0.25", 0.7) == 0.25


def test_number_value_rejects_invalid_values():
    with pytest.raises(ValueError, match="expected_number"):
        _number_value("bad", 0.7)


def test_optional_int_value_accepts_empty_or_valid_values():
    assert _optional_int_value(None) is None
    assert _optional_int_value("") is None
    assert _optional_int_value("12") == 12


def test_optional_int_value_rejects_invalid_values():
    with pytest.raises(ValueError, match="expected_int"):
        _optional_int_value("bad")


def test_runtime_schema_value_omits_empty_numeric_values_with_schema_defaults():
    assert (
        _runtime_schema_value(
            {"name": "max_relation_tokens", "type": "integer", "default": 360},
            "",
        )
        == (False, None)
    )
    assert (
        _runtime_schema_value(
            {"name": "threshold", "type": "number", "default": 0.5},
            None,
        )
        == (False, None)
    )


def test_runtime_schema_value_rejects_invalid_numeric_values():
    with pytest.raises(ValueError, match="expected_number"):
        _runtime_schema_value({"name": "threshold", "type": "number"}, "bad")


def test_load_context_keeps_model_row_id_once_converted():
    sdk = SimpleNamespace(
        models=SimpleNamespace(
            model_registry=SimpleNamespace(
                view=lambda row_id: {
                    "id": row_id,
                    "extra_config": {
                        "defaults": {"generation": {"temperature": 0.1}},
                        "test_config": {"prompt": "hello"},
                    },
                }
            )
        ),
        i18n=SimpleNamespace(t=lambda key: key),
    )

    ctx = {"model_row_id": "12", "form_id": "form", "form": {}}

    result = load_context(ctx, sdk)

    assert result is not None
    assert result.row_id == 12
    assert result.generation == {"temperature": 0.1}
    assert result.prompt == "hello"


@pytest.mark.asyncio
async def test_get_provider_accepts_none_warmup_result():
    provider = object()
    sdk = SimpleNamespace(
        ai=SimpleNamespace(
            get_provider_by_model_registry_id=lambda _row_id: _async_result(
                {"status": "ok", "provider": provider}
            ),
            warmup_provider=lambda _provider, *, wait: _async_result(None),
        )
    )

    resolved_provider, warmup_ms, error = await get_provider(sdk, 12)

    assert resolved_provider is provider
    assert warmup_ms is None
    assert error == ""


async def _async_result(value):
    return value
