from types import SimpleNamespace

from clients.qtdesktop.ui.messages import HandleInboundMessage
from clients.qtdesktop.ui.messages import HandleUserAction
from clients.qtdesktop.ui.messages import MessageDispatcher
from clients.qtdesktop.ui.messages import UserAction


def test_message_dispatcher_registers_and_dispatches_objects_and_dicts():
    calls = []
    dispatcher = MessageDispatcher()
    dispatcher.register("click", lambda payload: calls.append(("click", payload)))

    dispatcher.dispatch({"kind": "click", "payload": {"id": "btn"}})
    dispatcher.dispatch(SimpleNamespace(kind="click", payload={"id": "obj"}))
    dispatcher.dispatch({"kind": "missing", "payload": {"id": "no-op"}})

    assert calls == [
        ("click", {"id": "btn"}),
        ("click", {"id": "obj"}),
    ]


def test_desktop_message_handlers_dispatch_inbound_and_user_action():
    dispatch_calls = []
    dispatcher = SimpleNamespace(dispatch=lambda payload: dispatch_calls.append(payload))
    action = UserAction(
        name="demo.submit",
        surface_id="main",
        source_component_id="btn",
        context={"value": 1},
    )

    HandleInboundMessage(dispatcher).execute(
        SimpleNamespace(kind="click", payload={"id": "btn"})
    )
    HandleUserAction(dispatcher).execute(action)

    assert dispatch_calls == [
        {"kind": "click", "payload": {"id": "btn"}},
        {"kind": "user_action", "payload": action},
    ]
