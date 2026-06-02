from clients.qtdesktop.state import Store


def test_store_reads_page_before_global_when_scope_auto():
    store = Store()
    store.set("/status", "global-value", "global")
    store.set("/status", "page-value", "page")

    assert store.get("/status", scope="auto") == "page-value"
    assert store.get("/status", scope="global") == "global-value"
    assert store.get("/status", scope="page") == "page-value"


def test_store_clear_scope_only_removes_page_values():
    store = Store()
    store.set("/status", "global-value", "global")
    store.set("/filters/query", "ciao", "page")

    store.clear_scope("page")

    assert store.get("/status", scope="auto") == "global-value"
    assert store.get("/filters/query", default=None, scope="page") is None


def test_store_merge_keeps_nested_structure_and_leaf_reads():
    store = Store()

    store.merge({"system": {"modules": {"top": [{"id": "dashboard"}]}}}, "page")

    assert store.get("/system/modules/top", scope="page") == [{"id": "dashboard"}]
    assert store.snapshot() == {"system": {"modules": {"top": [{"id": "dashboard"}]}}}


def test_store_update_nested_values_preserves_sibling_global_state():
    store = Store()
    store.update(
        {
            "/core/supported_languages": [{"label": "EN", "value": "en"}],
            "/core/user/language": "en",
        },
        "global",
    )

    store.update(
        {"core": {"notifications": {"pending_count": 1, "view_path": "/system/notifications"}}},
        "global",
    )

    assert store.get("/core/notifications/pending_count", scope="global") == 1
    assert store.get("/core/supported_languages", scope="global") == [
        {"label": "EN", "value": "en"}
    ]
    assert store.get("/core/user/language", scope="global") == "en"
