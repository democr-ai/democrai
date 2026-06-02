from __future__ import annotations

from uuid import uuid4

from democrai.sdk.client import active_sdk as sdk


def module_media_url(filename: str) -> str:
    safe_name = filename.strip().lstrip("/")
    return str(sdk.media.get_public_url(f"assets/{safe_name}") or "")


def seed_messages() -> list[dict]:
    return [
        {
            "id": "chat_u_1",
            "role": "user",
            "kind": "text",
            "status": "completed",
            "content": {
                "text": "Can you compare the candidates for the next release?",
                "attachments": [
                    {
                        "name": "candidate-brief.pdf",
                        "mime_type": "application/pdf",
                        "storage_path": "assets/demo-doc.pdf",
                        "url": module_media_url("demo-doc.pdf"),
                    },
                    {
                        "name": "architecture.png",
                        "mime_type": "image/png",
                        "storage_path": "assets/demo-image.png",
                        "url": module_media_url("demo-image.png"),
                    },
                    {
                        "name": "raw-notes.txt",
                        "mime_type": "text/plain",
                        "storage_path": "assets/notes.txt",
                    },
                ],
            },
            "created_at": "2026-05-29T11:02:00",
        },
        {
            "id": "chat_a_1",
            "role": "assistant",
            "kind": "text",
            "status": "completed",
            "content": {
                "text": "Sure. I can show trends, priorities, and dependencies so you can make a quick decision.",
                "reasoning": "I considered impact, technical risk, and the time left before the release.",
            },
            "created_at": "2026-05-29T11:02:10",
        },
        {
            "id": "chat_tool_1",
            "role": "tool",
            "kind": "tool_result",
            "status": "completed",
            "content": {
                "tool_name": "release_risk_scan",
                "summary": "3 major risks found in the attached data.",
            },
            "created_at": "2026-05-29T11:02:20",
        },
        component_message("chat_component_seed", "chart", created_at="2026-05-29T11:02:25"),
        {
            "id": "chat_task_1",
            "role": "system",
            "kind": "task",
            "status": "running",
            "content": {
                "title": "Background analysis task",
            },
            "created_at": "2026-05-29T11:02:30",
        },
        {
            "id": "chat_u_2",
            "role": "user",
            "kind": "text",
            "status": "completed",
            "content": {"text": "Let's start with a summary of the main risks."},
            "created_at": "2026-05-29T11:03:00",
        },
        {
            "id": "chat_a_2",
            "role": "assistant",
            "kind": "text",
            "status": "completed",
            "content": {
                "text": "The main risks are UI regressions, query latency, and incomplete test coverage.",
                "reasoning": "I used severity x probability and roadmap timing to rank the risks.",
            },
            "created_at": "2026-05-29T11:03:10",
        },
    ]


def seed_threads() -> list[dict]:
    return [
        {
            "id": "release",
            "title": "Release planning",
            "snippet": "Risk summary",
            "preview": "Risk summary",
        },
        {
            "id": "sprint",
            "title": "Sprint review",
            "snippet": "Open actions",
            "preview": "Open actions",
        },
    ]


def seed_suggestions() -> list[dict]:
    return [
        {
            "label": "Summarize risks",
            "prompt": "Summarize the main release risks",
        },
        {
            "label": "Extract tasks",
            "prompt": "Extract open tasks from this thread",
        },
    ]


def append_component_for_kind(message_id: str, kind: str) -> dict:
    item_id = uuid4().hex[:8]
    normalized = kind.strip().lower() or "accordion"

    if normalized == "chart":
        return sdk.ui.Chart(
            f"{message_id}_chart_{item_id}",
            chart_type="bar",
            data=[21, 14, 8],
            labels=["High", "Medium", "Low"],
            title="Risk distribution",
        ).to_dict()

    if normalized == "table":
        return sdk.ui.DataTable(
            f"{message_id}_table_{item_id}",
            model=[
                {"id": "risk", "field": "risk", "label": "Risk", "type": "text", "editable": False},
                {"id": "owner", "field": "owner", "label": "Owner", "type": "text", "editable": False},
                {"id": "status", "field": "status", "label": "Status", "type": "text", "editable": False},
            ],
            rows=[
                {"id": "r1", "risk": "UI regression", "owner": "Frontend", "status": "Mitigating"},
                {"id": "r2", "risk": "Latency spikes", "owner": "Backend", "status": "Monitoring"},
            ],
            paginated=False,
        ).to_dict()

    return sdk.ui.Accordion(
        f"{message_id}_accordion_{item_id}",
        items=[
            {
                "id": f"{message_id}_acc_{item_id}",
                "title": "Execution notes",
                "content": "Rollback plan ready, with smoke tests focused on the critical APIs.",
                "open": True,
            }
        ],
        collapsible=True,
    ).to_dict()


def component_message(
    message_id: str, kind: str, *, created_at: str | None = None
) -> dict:
    component = append_component_for_kind(message_id, kind)
    message = {
        "id": message_id,
        "role": "assistant",
        "kind": "component",
        "status": "completed",
        "content": {"components": [component]},
    }
    if created_at is not None:
        message["created_at"] = created_at
    return message
