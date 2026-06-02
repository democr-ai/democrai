from __future__ import annotations

from typing import Any

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.actions.engine.model_tests.common import run_simple_provider_test
from modules.system.utils.actions.engine.model_test_support import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    _number_value,
    _response_text,
    _tool_call_test_tools,
)


@action("test_engine_model_tool_calling")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_tool_calling(ctx: dict[str, Any], module_sdk):
    async def execute(test_ctx, provider):
        options = {
            "temperature": _number_value(test_ctx.generation.get("temperature"), DEFAULT_TEMPERATURE),
            "top_p": _number_value(test_ctx.generation.get("top_p"), DEFAULT_TOP_P),
            "max_tokens": (
                int(test_ctx.generation["max_tokens"])
                if test_ctx.generation.get("max_tokens") not in (None, "")
                else None
            ),
            "tools": _tool_call_test_tools(),
            "tool_choice": str(test_ctx.payload.get("tool_choice") or "auto"),
        }
        response = await provider.generate_completion(
            messages=[{"role": "user", "content": test_ctx.prompt}],
            options=options,
        )
        content = _response_text(response)
        tool_call_count = len(getattr(response, "tool_calls", None) or [])
        output = content or f"tool_calls={tool_call_count}"
        return response, output, None

    return await run_simple_provider_test(
        ctx,
        module_sdk,
        method="tool_calling",
        require_prompt=True,
        execute=execute,
    )
