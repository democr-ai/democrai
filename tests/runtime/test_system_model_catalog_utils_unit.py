from __future__ import annotations

from types import SimpleNamespace

from modules.system.utils.actions.model.catalog import (
    catalog_statuses_from_inventory,
)


def test_catalog_statuses_include_active_downloads_and_strip_catalog_ids():
    sdk = SimpleNamespace(
        tasks=SimpleNamespace(
            get_tasks_by_key_prefix=lambda _prefix: [
                {
                    "status": "running",
                    "task_key": "system.model.catalog.download.catalog-b.123",
                }
            ]
        )
    )

    statuses = catalog_statuses_from_inventory(
        sdk,
        [{"catalog_model_id": " catalog-a ", "status": "active"}],
    )

    assert statuses == {
        "catalog-a": "available",
        "catalog-b": "downloading",
    }
