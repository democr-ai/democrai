from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import RuntimeNodeRegistry
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import app_ctx


RUNTIME_METRICS_STREAM_ID = "system.runtime.metrics.events"
RUNTIME_METRICS_SAMPLE_EVENT_NAME = "runtime.metrics.sample"


def get_runtime_metrics_node_id() -> str:
    ctx = app_ctx()
    configured = str(getattr(ctx, "node_id", "") or "").strip()
    if configured:
        return configured
    cfg = getattr(ctx, "config", None)
    if cfg is not None:
        configured = str(cfg.get("network.node_id", "") or "").strip()
        if configured:
            ctx.node_id = configured
            return configured
    ctx.node_id = SERVER_NAME
    return SERVER_NAME


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _percent(used: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((float(used) / float(total)) * 100.0, 1)


def _runtime_node_label(node_id: str) -> str:
    return node_id or SERVER_NAME


def _upsert_runtime_node(
    *,
    node_id: str,
    has_nvidia_gpu: bool | None = None,
    status: str = "active",
    seen: bool = True,
) -> None:
    if not node_id:
        return
    now = utc_now_naive()
    with SessionLocal() as session:
        row = (
            session.query(RuntimeNodeRegistry)
            .filter(RuntimeNodeRegistry.node_id == node_id)
            .first()
        )
        if row is None:
            row = RuntimeNodeRegistry(
                node_id=node_id,
                label=_runtime_node_label(node_id),
                status=status,
                hostname=SERVER_NAME,
                started_at=now,
                last_seen_at=now if seen else None,
                has_nvidia_gpu=False if has_nvidia_gpu is None else has_nvidia_gpu,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.label = row.label or _runtime_node_label(node_id)
            row.status = status
            row.hostname = row.hostname or SERVER_NAME
            if row.started_at is None:
                row.started_at = now
            if seen:
                row.last_seen_at = now
            if has_nvidia_gpu is not None:
                row.has_nvidia_gpu = has_nvidia_gpu
            row.updated_at = now
        session.commit()


def _mark_runtime_node_inactive() -> None:
    node_id = get_runtime_metrics_node_id()
    now = utc_now_naive()
    with SessionLocal() as session:
        row = (
            session.query(RuntimeNodeRegistry)
            .filter(RuntimeNodeRegistry.node_id == node_id)
            .first()
        )
        if row is not None:
            row.status = "inactive"
            row.updated_at = now
            session.commit()


def build_runtime_metrics_sample() -> dict[str, Any]:
    import psutil
    from democrai.core.platform.utils.system import get_resource_monitor

    vm = psutil.virtual_memory()
    resources = get_resource_monitor().get_resources()
    ram_total_mb = int(resources.get("ram_total_mb") or int(vm.total / (1024 * 1024)))
    ram_free_mb = int(resources.get("ram_free_mb") or int(vm.available / (1024 * 1024)))
    ram_used_mb = max(0, ram_total_mb - ram_free_mb)
    vram_total_mb = int(resources.get("vram_total_mb") or 0)
    vram_free_mb = int(resources.get("vram_free_mb") or 0)
    vram_used_mb = max(0, vram_total_mb - vram_free_mb)
    timestamp = _utc_now()

    return {
        "event_name": RUNTIME_METRICS_SAMPLE_EVENT_NAME,
        "node_id": get_runtime_metrics_node_id(),
        "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
        "label": timestamp.strftime("%H:%M:%S"),
        "cpu_percent": round(float(psutil.cpu_percent(interval=0.0) or 0.0), 1),
        "ram_total_mb": ram_total_mb,
        "ram_free_mb": ram_free_mb,
        "ram_used_mb": ram_used_mb,
        "ram_used_percent": round(float(vm.percent or _percent(ram_used_mb, ram_total_mb)), 1),
        "vram_total_mb": vram_total_mb,
        "vram_free_mb": vram_free_mb,
        "vram_used_mb": vram_used_mb,
        "vram_used_percent": _percent(vram_used_mb, vram_total_mb),
        "has_nvidia_gpu": bool(resources.get("has_nvidia_gpu")),
    }


def _runtime_metrics_interval_seconds() -> float:
    cfg = getattr(app_ctx(), "config", None)
    raw = cfg.get("runtime.metrics.interval_seconds", 1.0) if cfg is not None else 1.0
    try:
        interval = float(raw)
    except Exception:
        interval = 1.0
    return max(0.25, interval)


def _runtime_metrics_enabled() -> bool:
    cfg = getattr(app_ctx(), "config", None)
    raw = cfg.get("runtime.metrics.enabled", True) if cfg is not None else True
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)


async def _publish_runtime_metrics() -> None:
    network = getattr(app_ctx(), "network", None)
    if network is None or getattr(network, "stream_manager", None) is None:
        return
    interval = _runtime_metrics_interval_seconds()
    try:
        _upsert_runtime_node(node_id=get_runtime_metrics_node_id(), seen=False)
    except Exception as exc:
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.debug(
                f"[RuntimeMetrics] node registration skipped: {exc}",
                exc_info=True,
            )
    try:
        while True:
            try:
                sample = build_runtime_metrics_sample()
                _upsert_runtime_node(
                    node_id=sample["node_id"],
                    has_nvidia_gpu=sample["has_nvidia_gpu"],
                )
                await network.stream_manager.broadcast(
                    RUNTIME_METRICS_STREAM_ID,
                    sample,
                )
            except Exception as exc:
                logger = getattr(app_ctx(), "logger", None)
                if logger is not None:
                    logger.debug(
                        f"[RuntimeMetrics] sample skipped: {exc}",
                        exc_info=True,
                    )
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


def start_runtime_metrics_publisher() -> None:
    ctx = app_ctx()
    if getattr(ctx, "setup_mode", False) or not _runtime_metrics_enabled():
        return
    network = getattr(ctx, "network", None)
    loop = getattr(network, "_loop", None) if network is not None else None
    if loop is None:
        return
    existing = getattr(ctx, "runtime_metrics_publisher", None)
    if existing is not None and not existing.done():
        return
    ctx.runtime_metrics_publisher = asyncio.run_coroutine_threadsafe(
        _publish_runtime_metrics(),
        loop,
    )


def stop_runtime_metrics_publisher() -> None:
    task = getattr(app_ctx(), "runtime_metrics_publisher", None)
    if task is not None:
        task.cancel()
    try:
        _mark_runtime_node_inactive()
    except Exception:
        logger = getattr(app_ctx(), "logger", None)
        if logger is not None:
            logger.debug("[RuntimeMetrics] node inactive update skipped", exc_info=True)
    app_ctx().runtime_metrics_publisher = None
