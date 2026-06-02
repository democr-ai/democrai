from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from democrai.core.platform.utils.identity import to_optional_int


@dataclass
class BaseEffect:
    # init=False: subclasses set the correct kind via __post_init__, not via constructor arg
    kind: str = field(default="", init=False)


@dataclass
class NavigateEffect(BaseEffect):
    path: str
    render: bool = True

    def __post_init__(self):
        self.kind = "navigate"


@dataclass
class RenderEffect(BaseEffect):
    path: Optional[str] = None

    def __post_init__(self):
        self.kind = "render"


@dataclass
class UiMessagesEffect(BaseEffect):
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        self.kind = "ui_messages"


@dataclass
class StartPipelineEffect(BaseEffect):
    task: Any
    label: str
    args: Optional[Dict[str, Any]] = None
    module: Optional[str] = None

    def __post_init__(self):
        self.kind = "pipeline"
        if self.args is None:
            self.args = {}


@dataclass
class ConfirmEffect(BaseEffect):
    via: str = "dialog"
    path: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    render: bool = True

    def __post_init__(self):
        self.kind = "confirm"
        if self.params is None:
            self.params = {}


@dataclass
class NotifyEffect(BaseEffect):
    channel: str
    payload: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[int] = None
    organization_id: Optional[int] = None

    def __post_init__(self):
        self.kind = "notify"


@dataclass
class RefreshModulesEffect(BaseEffect):
    def __post_init__(self):
        self.kind = "refresh_modules"


@dataclass
class ScrollEffect(BaseEffect):
    component_id: str

    def __post_init__(self):
        self.kind = "scroll"


@dataclass
class SetJwtEffect(BaseEffect):
    token: str

    def __post_init__(self):
        self.kind = "set_jwt"


A2UI_MESSAGE_KEYS = {
    "surfaceUpdate",
    "beginRendering",
    "propertyUpdate",
    "dataModelUpdate",
    "windowAction",
    "current_path",
}


def effects_from_action_result(
    result: Dict[str, Any],
    *,
    action_name: str,
    action_context: Optional[Dict[str, Any]] = None,
) -> List[BaseEffect]:
    """
    Converts module action output into typed effects.
    Supports both:
    - New explicit format: {"effects":[...]}
    - Legacy format: {"refresh":True, "scroll_to":"...", ...}
    """
    explicit = result.get("effects")
    if isinstance(explicit, list):
        effects = [_parse_effect_descriptor(e, action_name) for e in explicit]
        return [e for e in effects if e is not None]

    effects: List[BaseEffect] = []

    if "navigate" in result and isinstance(result["navigate"], str):
        effects.append(NavigateEffect(result["navigate"], render=True))
    if "path" in result and result.get("op") == "navigate":
        effects.append(NavigateEffect(result["path"], render=True))

    if result.get("ok") is False and "Missing AI dependency" in result.get("error", ""):
        dependency = result["error"].split(": ")[-1]
        effects.append(
            NotifyEffect(
                channel="toast",
                payload={
                    "kind": "toast",
                    "variant": "error",
                    "title": "Missing dependency",
                    "text": f"Missing AI dependency: {dependency}",
                },
            )
        )

    pipeline = result.get("pipeline")
    if pipeline is not None:
        effects.extend(_parse_pipeline_legacy(pipeline, action_name))

    notify = result.get("notify")
    if notify is not None:
        effects.extend(_parse_notify_legacy(notify))

    if result.get("refresh", False):
        effects.append(RenderEffect())

    if result.get("refresh_modules", False):
        effects.append(RefreshModulesEffect())

    scroll_to = result.get("scroll_to")
    if isinstance(scroll_to, str) and scroll_to:
        effects.append(ScrollEffect(scroll_to))

    if "jwt" in result and result["jwt"] is not None:
        effects.append(SetJwtEffect(str(result["jwt"])))

    if isinstance(result.get("messages"), list):
        messages = [m for m in result["messages"] if isinstance(m, dict)]
        if messages:
            effects.append(UiMessagesEffect(messages))
    elif isinstance(result.get("message"), dict):
        effects.append(UiMessagesEffect([result["message"]]))

    if any(k in result for k in A2UI_MESSAGE_KEYS):
        effects.append(UiMessagesEffect([result]))

    return effects


def _parse_effect_descriptor(raw: Any, action_name: str) -> Optional[BaseEffect]:
    if isinstance(raw, BaseEffect):
        return raw
    if not isinstance(raw, dict):
        return None

    effect_type = raw.get("type")
    if effect_type is None:
        if any(k in raw for k in A2UI_MESSAGE_KEYS):
            return UiMessagesEffect([raw])
        return None

    if effect_type == "navigate":
        path = raw.get("path")
        if isinstance(path, str):
            return NavigateEffect(path, render=bool(raw.get("render", True)))
    elif effect_type == "render":
        path = raw.get("path")
        return RenderEffect(path if isinstance(path, str) else None)
    elif effect_type == "ui_messages":
        messages = raw.get("messages", [])
        if isinstance(messages, list):
            return UiMessagesEffect([m for m in messages if isinstance(m, dict)])
    elif effect_type == "window_action":
        payload = {k: v for k, v in raw.items() if k != "type"}
        if payload:
            return UiMessagesEffect([{"windowAction": payload}])
    elif effect_type == "pipeline":
        task = raw.get("task")
        label = raw.get("label", "Pipeline")
        args = raw.get("args", {})
        module = raw.get("module")
        if task is not None and isinstance(label, str):
            return StartPipelineEffect(
                task=task,
                label=label,
                args=args if isinstance(args, dict) else {},
                module=module
                if isinstance(module, str)
                else _guess_module_name(action_name),
            )
    elif effect_type == "confirm":
        via = raw.get("via", "dialog")
        path = raw.get("path")
        params = raw.get("params", {})
        return ConfirmEffect(
            via=via if isinstance(via, str) else "dialog",
            path=path if isinstance(path, str) else None,
            params=params if isinstance(params, dict) else {},
            render=bool(raw.get("render", True)),
        )
    elif effect_type == "notify":
        channel = raw.get("channel")
        payload = raw.get("payload", {})
        user_id = to_optional_int(raw.get("user_id"))
        organization_id = to_optional_int(raw.get("organization_id"))
        if isinstance(channel, str) and isinstance(payload, dict):
            return NotifyEffect(
                channel=channel,
                payload=payload,
                user_id=user_id,
                organization_id=organization_id,
            )
    elif effect_type == "refresh_modules":
        return RefreshModulesEffect()
    elif effect_type == "scroll":
        component_id = raw.get("component_id")
        if isinstance(component_id, str):
            return ScrollEffect(component_id)
    elif effect_type == "set_jwt":
        token = raw.get("token")
        if token is not None:
            return SetJwtEffect(str(token))

    return None


def _parse_pipeline_legacy(
    pipeline_raw: Any, action_name: str
) -> List[StartPipelineEffect]:
    out: List[StartPipelineEffect] = []
    items = pipeline_raw if isinstance(pipeline_raw, list) else [pipeline_raw]
    for item in items:
        if isinstance(item, dict):
            task = item.get("task")
            label = item.get("label", "Pipeline")
            args = item.get("args", {})
            module = item.get("module") or _guess_module_name(action_name)
            if task is not None and isinstance(label, str):
                out.append(
                    StartPipelineEffect(
                        task=task,
                        label=label,
                        args=args if isinstance(args, dict) else {},
                        module=module if isinstance(module, str) else None,
                    )
                )
    return out


def _parse_notify_legacy(notify_raw: Any) -> List[NotifyEffect]:
    out: List[NotifyEffect] = []
    items = notify_raw if isinstance(notify_raw, list) else [notify_raw]
    for item in items:
        if not isinstance(item, dict):
            continue
        channel = item.get("channel")
        payload = item.get("payload", {})
        user_id = to_optional_int(item.get("user_id"))
        organization_id = to_optional_int(item.get("organization_id"))
        if isinstance(channel, str) and isinstance(payload, dict):
            out.append(
                NotifyEffect(
                    channel=channel,
                    payload=payload,
                    user_id=user_id,
                    organization_id=organization_id,
                )
            )
    return out


def _guess_module_name(action_name: str) -> Optional[str]:
    if "." not in action_name:
        return None
    return action_name.split(".", 1)[0]
