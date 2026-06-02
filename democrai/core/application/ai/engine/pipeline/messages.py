from __future__ import annotations

import contextlib
from typing import Any, AsyncIterator

from democrai.core.application.ai.engine.pipeline.options import string_list
from democrai.core.application.ai.engine.schemas.completion import ContentPart
from democrai.core.application.ai.engine.schemas.completion import Message
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.pipeline_context import current_ai_pipeline_context
from democrai.core.application.ai.security.prompt.builder import PromptContextBuilder
from democrai.core.application.ai.security.prompt.messages import (
    normalize_prompt_messages_with_audit,
)
from democrai.core.platform.agents.registry import skill_registry
from democrai.core.platform.agents.skills import SkillLoader
from democrai.core.runtime.foundation.app import app_ctx


async def messages_with_selected_skills(messages: list[Any], options: Any) -> list[Any]:
    if not isinstance(options, dict):
        return messages
    selected_skills = string_list(options.get("skills"))
    if not selected_skills:
        return messages

    context = current_ai_pipeline_context()
    if context is not None:
        context.selected_skills = tuple(selected_skills)

    async with ai_pipeline_step(
        type="skill.resolve",
        name="selected",
        input={"skills": selected_skills},
    ) as step:
        skills = []
        for name in selected_skills:
            skill = skill_registry.get(name)
            if skill is None:
                raise ValueError(f"skill_not_found:{name}")
            skills.append(skill)
        if isinstance(step, dict):
            step["output"] = {
                "skills": [skill.metadata.name for skill in skills],
            }

    rendered = SkillLoader.render_activated_skills(skills)
    async with ai_pipeline_step(
        type="skill.injected",
        name="messages",
        input={"skills": [skill.metadata.name for skill in skills]},
    ) as step:
        prompt_builder = PromptContextBuilder()
        skill_messages = await normalize_prompt_messages_with_audit(
            [
                prompt_builder.skill_instruction(
                    rendered,
                    origin=",".join(skill.metadata.name for skill in skills),
                )
            ],
            stage="skill_injection",
        )
        resolved_messages = [
            *skill_messages,
            *messages,
        ]
        if isinstance(step, dict):
            step["output"] = {"messages": len(resolved_messages)}
    return resolved_messages


@contextlib.asynccontextmanager
async def materialized_pipeline_messages(
    messages: Any,
    *,
    engine_id: str | None,
) -> AsyncIterator[list[Any]]:
    del engine_id
    original_messages = await normalize_prompt_messages_with_audit(
        list(messages or []),
        stage="media_materialization",
    )
    if not _messages_have_storage_path(original_messages):
        yield original_messages
        return

    async with ai_pipeline_step(
        type="media.materialized",
        name="messages",
        input={"items": _message_storage_path_count(original_messages)},
    ) as step:
        media = getattr(app_ctx(), "media", None)
        if media is None:
            raise RuntimeError("media_provider_unavailable")
        resolved_messages = _materialize_message_media(
            original_messages,
            media=media,
        )
        if isinstance(step, dict):
            step["output"] = {"items": _message_storage_path_count(original_messages)}

    yield resolved_messages


def _messages_have_storage_path(messages: list[Any]) -> bool:
    return _message_storage_path_count(messages) > 0


def _message_storage_path_count(messages: list[Message]) -> int:
    count = 0
    for message in messages:
        content = message.content
        if content is None or isinstance(content, str):
            continue
        for part in content:
            if _content_part_storage_path(part):
                count += 1
    return count


def _materialize_message_media(
    messages: list[Message],
    *,
    media: Any,
) -> list[Message]:
    resolved: list[Message] = []
    for message in messages:
        content = message.content
        if content is None or isinstance(content, str):
            resolved.append(message)
            continue
        resolved_content = [
            _materialize_content_part(
                part,
                media=media,
            )
            for part in content
        ]
        resolved.append(message.model_copy(update={"content": resolved_content}))
    return resolved


def _materialize_content_part(
    part: ContentPart,
    *,
    media: Any,
) -> ContentPart:
    storage_path = _content_part_storage_path(part)
    if not storage_path:
        return part
    return part.model_copy(update={"data": bytes(media.load(storage_path))})


def _content_part_storage_path(part: ContentPart) -> str:
    return str(part.storage_path or "").strip()
