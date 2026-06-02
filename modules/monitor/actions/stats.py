from __future__ import annotations

from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


_SERIES: dict[tuple[str, str], dict[str, list[Any]]] = {}


def _append_window(items: list[Any], value: Any, window: int) -> list[Any]:
    items.append(value)
    limit = max(1, int(window or 45))
    if len(items) > limit:
        items[:] = items[-limit:]
    return list(items)


def _format_gb(value_mb: int) -> str:
    return f"{(float(value_mb or 0) / 1024.0):.1f} GB"


@action("runtime_metrics_sample")
@permission_required(["monitor.view"])
async def runtime_metrics_sample(ctx: dict, session: dict, module_sdk):
    payload = ctx.get("payload") if isinstance(ctx.get("payload"), dict) else {}
    context = ctx.get("context") if isinstance(ctx.get("context"), dict) else {}
    expected_node_id = str(context.get("node_id") or "").strip()
    node_id = str(payload.get("node_id") or "").strip()
    if not expected_node_id or node_id != expected_node_id:
        return {"values": {}}

    node_key = str(context.get("node_key") or "").strip()
    if not node_key:
        return {"values": {}}
    window = int(context.get("window") or 45)
    binding_id = str(ctx.get("binding_id") or node_key).strip()
    series = _SERIES.setdefault(
        (binding_id, node_key),
        {
            "labels": [],
            "cpu": [],
            "ram": [],
            "vram": [],
        },
    )

    label = str(payload.get("label") or "")
    cpu_percent = round(float(payload.get("cpu_percent") or 0.0), 1)
    ram_percent = round(float(payload.get("ram_used_percent") or 0.0), 1)
    vram_percent = round(float(payload.get("vram_used_percent") or 0.0), 1)
    ram_used_mb = int(payload.get("ram_used_mb") or 0)
    ram_total_mb = int(payload.get("ram_total_mb") or 0)
    vram_used_mb = int(payload.get("vram_used_mb") or 0)
    vram_total_mb = int(payload.get("vram_total_mb") or 0)
    has_nvidia_gpu = bool(payload.get("has_nvidia_gpu"))
    base_path = f"/monitor_stats/nodes/{node_key}"

    labels = _append_window(series["labels"], label, window)
    return {
        "values": {
            f"{base_path}/latest/node_id": node_id,
            f"{base_path}/latest/cpu": f"{cpu_percent:.1f}%",
            f"{base_path}/latest/ram": (
                f"{_format_gb(ram_used_mb)} / {_format_gb(ram_total_mb)} "
                f"({ram_percent:.1f}%)"
            ),
            f"{base_path}/latest/vram": (
                f"{_format_gb(vram_used_mb)} / {_format_gb(vram_total_mb)} "
                f"({vram_percent:.1f}%)"
                if has_nvidia_gpu and vram_total_mb > 0
                else "N/A"
            ),
            f"{base_path}/cpu/data": _append_window(
                series["cpu"], cpu_percent, window
            ),
            f"{base_path}/cpu/labels": labels,
            f"{base_path}/ram/data": _append_window(
                series["ram"], ram_percent, window
            ),
            f"{base_path}/ram/labels": labels,
            f"{base_path}/vram/data": _append_window(
                series["vram"], vram_percent, window
            ),
            f"{base_path}/vram/labels": labels,
        }
    }
