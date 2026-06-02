from __future__ import annotations

from democrai.sdk.auth import permission_required
import asyncio

from democrai.sdk.decorators import action
from democrai.sdk.client import active_sdk as sdk


async def _run_demo_task(module_sdk, task_ref: dict) -> None:
    steps = 10
    for i in range(1, steps + 1):
        await asyncio.sleep(1.5)
        task_id = task_ref["task_id"]
        if task_id:
            await module_sdk.tasks.update_progress(
                task_id,
                i / steps,
                label=f"Processing step {i}/{steps}...",
            )


@action("components.start_bg_task_demo")
@permission_required(["components.documentation.view"])
async def start_bg_task_demo(ctx: dict, session: dict, module_sdk) -> dict:
    task_ref: dict = {"task_id": ""}

    task_id = await module_sdk.tasks.run_background(
        _run_demo_task(module_sdk, task_ref),
        label="Demo Background Task",
        task_key="test_background_task",
    )
    task_ref["task_id"] = task_id

    card = sdk.ui.BackgroundTask(f"bg_task_card_{task_id}", task_id=task_id)

    return module_sdk.effects.respond(
        module_sdk.effects.ui_collection_append(
            "bg_task_demo_container",
            "children",
            card.to_dict(),
            surface_id=str(ctx.get("_surface_id") or "main").strip() or "main",
        )
    )
