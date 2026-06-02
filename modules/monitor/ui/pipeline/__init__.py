from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from modules.monitor.utils.ui.tables import table_state_from_params, translated_table_model


@permission_required(["monitor.view"])
async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/pipeline")
    table = builder.get_component("monitor_pipeline_table")
    if table is not None:
        page, page_size, filters, sort = table_state_from_params(
            params,
            "monitor_pipeline_table",
            default_sort_field="timestamp",
        )
        table.set_property(
            "model",
            translated_table_model(
                sdk,
                sdk.models.ai_model_pipeline_steps.table_model(),
            ),
        )
        table.set_property("page", page)
        table.set_property("page_size", page_size)
        table.set_property("filters", filters)
        table.set_property("sort", sort)

    return builder
