from __future__ import annotations

from typing import Any

from democrai.sdk.dependencies import ensure_import
from democrai.sdk.engines import get_chat_template

CHAT_HANDLERS_MAP = {
    "llava15": "Llava15ChatHandler",
    "mtmd": "Qwen25VLChatHandler",
    "qwen25vl": "Qwen25VLChatHandler",
}


def build_chat_handler(llm: Any, config: dict[str, Any]) -> Any:
    template = resolve_chat_template(config)
    if not template:
        return None

    chat_format = ensure_import(
        "llama_cpp.llama_chat_format",
        dependency_key="llama_cpp",
    )
    eos_token_id = llm.token_eos()
    bos_token_id = llm.token_bos()
    formatter = chat_format.Jinja2ChatFormatter(
        template=template,
        eos_token=llama_token_text(llm, eos_token_id),
        bos_token=llama_token_text(llm, bos_token_id),
        stop_token_ids=[eos_token_id] if eos_token_id != -1 else None,
    )
    return ChatTemplateHandler(formatter.to_chat_handler())


def build_multimodal_chat_handler(config: dict[str, Any]) -> Any:
    auxiliary_paths = (
        config.get("auxiliary_paths")
        if isinstance(config.get("auxiliary_paths"), dict)
        else {}
    )
    mmproj_path = str(auxiliary_paths.get("mmproj") or "").strip()
    if not mmproj_path:
        return None

    chat_format = ensure_import(
        "llama_cpp.llama_chat_format",
        dependency_key="llama_cpp",
    )
    handler_cls = multimodal_chat_handler_class(chat_format, config)
    if handler_cls is None:
        raise ValueError("llamacpp_multimodal_handler_unavailable")

    template = resolve_chat_template(config)
    has_custom_template = bool(template)
    if has_custom_template:
        handler_cls = type(
            f"Custom{handler_cls.__name__}",
            (handler_cls,),
            {"CHAT_FORMAT": template},
        )
    handler = handler_cls(
        clip_model_path=mmproj_path,
        verbose=bool(config.get("verbose", False)),
    )
    if has_custom_template:
        handler.chat_format_template = template
        handler.template_options = {}
    elif str(config.get("multimodal_chat_handler") or "").strip().lower() == "qwen25vl":
        handler.chat_format_template = _qwen25vl_thinking_template(handler.CHAT_FORMAT)
        handler.template_options = {}
    return handler


class ChatTemplateHandler:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.template_options: dict[str, Any] = {}

    def __call__(self, **kwargs: Any) -> Any:
        return self.handler(**{**kwargs, **self.template_options})


def chat_handler_with_template_options(llm: Any, options: dict[str, Any]) -> Any:
    chat_format = ensure_import(
        "llama_cpp.llama_chat_format",
        dependency_key="llama_cpp",
    )
    handler = (
        getattr(llm, "chat_handler", None)
        or getattr(llm, "_chat_handlers", {}).get(getattr(llm, "chat_format", None))
        or chat_format.get_chat_completion_handler(getattr(llm, "chat_format", None))
    )

    def _handler_with_options(*args: Any, **kwargs: Any) -> Any:
        return handler(*args, **{**options, **kwargs})

    return _handler_with_options


def set_template_options(handler: Any, options: dict[str, Any]) -> None:
    if hasattr(handler, "template_options"):
        handler.template_options = dict(options)
    template = getattr(handler, "chat_format_template", None)
    if isinstance(template, str):
        if "enable_thinking" in options:
            value = "true" if bool(options["enable_thinking"]) else "false"
            handler.CHAT_FORMAT = f"{{%- set enable_thinking = {value} -%}}\n{template}"
        else:
            handler.CHAT_FORMAT = template


def _qwen25vl_thinking_template(template: str) -> str:
    thinking_prompt = (
        "{% if enable_thinking is defined and enable_thinking %}"
        "/think\n"
        "{% elif enable_thinking is defined and not enable_thinking %}"
        "/no_think\n"
        "{% endif %}"
    )
    text_prompt = "{{ content['text'] }}"
    if text_prompt not in template:
        return template
    return template.replace(text_prompt, thinking_prompt + text_prompt, 1)


def resolve_chat_template(config: dict[str, Any]) -> str:
    template_name = str(config.get("chat_template") or "").strip()
    definition = get_chat_template(template_name)
    if definition is None:
        return ""
    template = str(definition.get("template") or "")
    if not template:
        raise ValueError(f"missing_chat_template:{template_name}")
    return template


def llama_token_text(llm: Any, token_id: int) -> str:
    if token_id == -1:
        return ""
    return str(llm._model.token_get_text(token_id))


def multimodal_chat_handler_class(chat_format: Any, config: dict[str, Any]) -> Any:
    handler_name = str(config.get("multimodal_chat_handler") or "").strip().lower()

    class_name = CHAT_HANDLERS_MAP.get(handler_name)
    if class_name is None:
        raise ValueError("missing_or_unsupported_multimodal_chat_handler")
    return getattr(chat_format, class_name, None)
