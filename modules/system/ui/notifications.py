from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk as sdk


def _safe_suffix(value: str) -> str:
    return (
        "".join(ch if ch.isalnum() else "_" for ch in str(value or "")).strip("_")
        or "item"
    )


def _wrap_long_text(value: str, chunk_size: int = 68, max_lines: int = 4) -> str:
    text = str(value or "")
    if not text:
        return ""
    compact = text.replace("\r", "").replace("\n", "")
    if len(compact) <= chunk_size:
        return compact
    lines = [compact[i : i + chunk_size] for i in range(0, len(compact), chunk_size)]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "..."
    return "\n".join(lines)


def _t(key: str, fallback: str, context: dict[str, Any] | None = None) -> str:
    translated = sdk.i18n.t(key, context=context)
    if translated == key:
        return fallback
    return translated


def _badge(
    builder: Any,
    component_id: str,
    text: str,
    *,
    variant: str = "secondary",
) -> str:
    builder.add(sdk.ui.Badge(component_id, text, variant=variant))
    return component_id


def _meta_row(builder: Any, item: dict[str, Any], suffix: str) -> str:
    badges: list[str] = []
    resource_type = str(item.get("resource_type") or sdk.access.EXTERNAL_RESOURCE_NETWORK)
    operation = str(item.get("operation") or "")
    subject_type = str(item.get("subject_type") or "module")
    subject_name = str(item.get("subject_name") or item.get("module_name") or "")
    session_key = str(item.get("session_key") or "").strip()
    resume_action = str(item.get("resume_action") or "").strip()

    badges.append(_badge(builder, f"sys_notif_type_{suffix}", f"{resource_type}:{operation}"))
    if subject_name:
        badges.append(_badge(builder, f"sys_notif_subject_{suffix}", f"{subject_type}:{subject_name}"))
    if session_key:
        badges.append(
            _badge(
                builder,
                f"sys_notif_session_badge_{suffix}",
                _t("system.notifications.session_scoped", "session"),
                variant="info",
            )
        )
    else:
        badges.append(
            _badge(
                builder,
                f"sys_notif_no_session_badge_{suffix}",
                _t("system.notifications.no_session", "no session"),
                variant="warning",
            )
        )
    if resume_action:
        badges.append(
            _badge(
                builder,
                f"sys_notif_resume_badge_{suffix}",
                _t("system.notifications.resumable", "resumable"),
                variant="success",
            )
        )

    row_id = f"sys_notif_meta_{suffix}"
    row = sdk.ui.Row(row_id, badges)
    row.set_property("spacing", 6)
    row.set_property("align", "left")
    builder.add(row)
    return row_id


def _text_line(
    builder: Any,
    component_id: str,
    label: str,
    value: str,
    *,
    mono: bool = False,
) -> str:
    text = f"{label}\n{value}" if value else label
    builder.add(sdk.ui.Text(component_id, text))
    style = "font-size: 12px;"
    if mono:
        style += " font-family: monospace;"
    builder.get_component(component_id).set_property("style", style)
    return component_id


def _external_access_item(builder: Any, item: dict[str, Any], suffix: str) -> list[str]:
    children: list[str] = []
    subject_type = str(item.get("subject_type") or "module")
    subject_name = str(item.get("subject_name") or item.get("module_name") or "")
    target = str(item.get("target") or "")
    session_key = str(item.get("session_key") or "").strip() or None
    resource_type = str(item.get("resource_type") or sdk.access.EXTERNAL_RESOURCE_NETWORK)
    operation = str(item.get("operation") or "")
    resume_action = str(item.get("resume_action") or "").strip()

    children.append(_meta_row(builder, item, suffix))
    if target:
        children.append(
            _text_line(
                builder,
                f"sys_notif_target_{suffix}",
                _t("system.notifications.target", "Target"),
                _wrap_long_text(target),
                mono=True,
            )
        )
    if resume_action:
        children.append(
            _text_line(
                builder,
                f"sys_notif_resume_action_{suffix}",
                _t("system.notifications.resume_action", "Resume action"),
                resume_action,
            )
        )

    approve_session_id = f"sys_notif_session_{suffix}"
    approve_permanent_id = f"sys_notif_permanent_{suffix}"
    deny_id = f"sys_notif_deny_{suffix}"
    actions_id = f"sys_notif_actions_{suffix}"

    params = {
        "subject_type": subject_type,
        "subject_name": subject_name,
        "target": target,
        "resource_type": resource_type,
        "operation": operation,
        "notification_card_id": f"sys_notif_item_card_{suffix}",
    }
    action_buttons: list[str] = []
    if session_key:
        params["request_session_key"] = session_key
        builder.add(
            sdk.ui.Button(
                approve_session_id,
                _t("system.notifications.approve_session", "Approve for session"),
                action="approve_external_access",
                params={**params, "decision": "session"},
                variant="default",
            )
        )
        action_buttons.append(approve_session_id)
    builder.add(
        sdk.ui.Button(
            approve_permanent_id,
            _t("system.notifications.approve_permanent", "Approve permanently"),
            action="approve_external_access",
            params={**params, "decision": "permanent"},
            variant="primary",
        )
    )
    action_buttons.append(approve_permanent_id)
    builder.add(
        sdk.ui.Button(
            deny_id,
            _t("system.notifications.deny", "Deny"),
            action="approve_external_access",
            params={**params, "decision": "deny"},
            variant="danger",
        )
    )
    action_buttons.append(deny_id)

    actions = sdk.ui.Row(actions_id, action_buttons)
    actions.set_property("align", "left")
    actions.set_property("spacing", 8)
    actions.set_property("style", "margin-top: 10px;")
    builder.add(actions)
    children.append(actions_id)
    return children


async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/notifications")
    pending = sdk.system.notifications.list()
    builder.set_store(
        "/core/notifications/pending_count",
        len(pending),
        scope="global",
    )
    builder.set_store(
        "/core/notifications/view_path",
        sdk.system.notifications.center_view_path(),
        scope="global",
    )

    list_children: list[str] = []
    if not pending:
        builder.add(
            sdk.ui.Text(
                "sys_notif_empty",
                _t("system.notifications.empty", "No pending notifications."),
            )
        )
        list_children.append("sys_notif_empty")
    else:
        for index, item in enumerate(pending):
            suffix = _safe_suffix(
                f"{item.get('module_name')}_{item.get('target')}_{index}"
            )
            title_id = f"sys_notif_item_title_{suffix}"
            card_id = f"sys_notif_item_card_{suffix}"

            builder.add(
                sdk.ui.Title(
                    title_id,
                    _t(
                        "system.notifications.external_access_request",
                        "External access request",
                    ),
                    4,
                )
            )
            body_children: list[str] = [title_id]
            body_children.extend(_external_access_item(builder, item, suffix))

            card = sdk.ui.Card(card_id, body_children, variant="elevated")
            card.set_property("padding", [14, 14, 14, 14])
            card.set_property("style", "width: 100%;")
            builder.add(card)
            list_children.append(card_id)

    notifications_list = builder.get_component("sys_notif_list")
    if notifications_list is not None:
        notifications_list.set_children(list_children)
    return builder
