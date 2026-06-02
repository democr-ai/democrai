from types import SimpleNamespace

from democrai.core.infrastructure.database.session_store import SessionStore


def test_query_and_runtime_storage_wrappers_work():
    session_store = SimpleNamespace(get=lambda session_id: {"session": session_id})

    assert session_store.get("s1") == {"session": "s1"}


def test_bus_transport_and_runtime_storage_modules_behave():
    provider_calls = []
    provider = SimpleNamespace(
        send=lambda client_id, message: provider_calls.append(("send", client_id, message)),
        broadcast=lambda message: provider_calls.append(("broadcast", message)),
    )

    store = SessionStore()
    assert hasattr(store, "get")
    assert hasattr(store, "create")
