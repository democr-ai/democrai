from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.monitor.utils.actions.tables import list_remote_table


@action("list_tasks")
@permission_required(["monitor.view"])
async def list_tasks(ctx: dict, session: dict, module_sdk):
    return list_remote_table(
        ctx,
        session,
        module_sdk,
        model_name="background_tasks",
        table_id_default="monitor_tasks_table",
        default_sort_field="updated_at",
    )
