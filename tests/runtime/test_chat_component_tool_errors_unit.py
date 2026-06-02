from __future__ import annotations

from modules.chat.actions.conversation import _component_payload_from_tool_response


def test_component_tool_error_response_becomes_alert_payload():
    payload = _component_payload_from_tool_response(
        {
            "type": "tool.response",
            "name": "chat.show-table",
            "payload": {
                "result": {
                    "status": "error",
                    "error": "invalid_component_schema",
                    "message": "rows are required",
                    "path": "component.DataTable.rows",
                }
            },
        }
    )

    assert payload["component_kind"] == "Alert"
    component = payload["components"][0]
    props = component["component"]["Alert"]
    assert props["title"]["literalString"] == "Component error"
    assert props["variant"] == "destructive"
    assert props["description"]["literalString"] == (
        "invalid_component_schema\n"
        "rows are required\n"
        "path: component.DataTable.rows"
    )
