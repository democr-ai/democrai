from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QScrollArea

from clients.qtdesktop.ui.renderers.domains.data.sequence_diagram import (
    SequenceDiagramRenderer,
    _parse_mermaid_sequence,
    _normalize_participants_and_messages,
)


def test_normalize_participants_and_messages_infers_participants():
    participants, messages = _normalize_participants_and_messages(
        {
            "participants": [{"id": "client", "label": "Client"}],
            "messages": [
                {"from": "client", "to": "gateway", "text": "POST /chat"},
                {"from": "gateway", "to": "client", "text": "ok", "type": "reply"},
            ],
        }
    )

    ids = [participant.id for participant in participants]
    assert "client" in ids
    assert "gateway" in ids
    assert len(messages) == 2


def test_sequence_diagram_renderer_mounts_scroll_view():
    app = QApplication.instance() or QApplication([])
    renderer = SequenceDiagramRenderer()
    widget = renderer.render(
        {
            "title": "Flow",
            "participants": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "messages": [{"from": "a", "to": "b", "text": "hello"}],
            "height": 300,
        },
        "main",
        SimpleNamespace(),
        comp_id="sequence",
    )

    scroll = widget.layout().itemAt(1).widget()
    assert isinstance(scroll, QScrollArea)
    assert scroll.widget() is not None
    app.processEvents()


def test_normalize_participants_and_messages_accepts_mermaid():
    participants, messages = _normalize_participants_and_messages(
        {
            "mermaid": """
sequenceDiagram
    participant Client
    participant Server
    Client->>Server: ping
    Server-->>Client: pong
""",
        }
    )

    ids = [participant.id for participant in participants]
    assert "Client" in ids
    assert "Server" in ids
    assert len(messages) == 2
    assert messages[1].msg_type == "reply"
    parsed_participants, parsed_messages = _parse_mermaid_sequence("sequenceDiagram\nA->>B: hi")
    assert len(parsed_participants) == 2
    assert parsed_messages[0]["text"] == "hi"
