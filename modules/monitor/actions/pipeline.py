from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.monitor.utils.actions.tables import list_remote_table


@action("list_pipeline_steps")
@permission_required(["monitor.view"])
async def list_pipeline_steps(ctx: dict, session: dict, module_sdk):
    return list_remote_table(
        ctx,
        session,
        module_sdk,
        model_name="ai_model_pipeline_steps",
        table_id_default="monitor_pipeline_table",
        default_sort_field="timestamp",
    )
