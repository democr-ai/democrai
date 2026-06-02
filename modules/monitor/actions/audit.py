from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.monitor.utils.actions.tables import list_remote_table


@action("list_audit")
@permission_required(["monitor.view"])
async def list_audit(ctx: dict, session: dict, module_sdk):
    return list_remote_table(
        ctx,
        session,
        module_sdk,
        model_name="audit_events",
        table_id_default="monitor_audit_table",
        default_sort_field="timestamp",
    )
