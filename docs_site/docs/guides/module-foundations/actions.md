# Actions

Actions live under `modules/<module>/actions/` and are registered with the SDK
decorator:

```python
from pydantic import BaseModel, Field

from democrai.sdk.decorators import action, validate
from democrai.sdk.auth import permission_required


class MessageFormPayload(BaseModel):
    text: str = Field(min_length=1)


class SubmitMessagePayload(BaseModel):
    message_form: MessageFormPayload


@action("submit_message")
@validate(SubmitMessagePayload, strip_extra=True)
@permission_required(["chat.write"])
async def submit_message(ctx: dict, session: dict, module_sdk):
    values = ctx["message_form"]
    text = values["text"]
    ...
```

The registered action name is module-qualified at runtime, so YAML calls it as
`chat.submit_message`.

An action should:

- validate the payload received from the client with `@validate(...)` when the
  payload shape is stable;
- use `module_sdk.database` for module-owned records;
- use public SDK domains for platform services;
- return `module_sdk.effects.respond(...)`;
- keep UI updates explicit through effects such as navigation, render,
  property updates, collection updates, or state patches.

For Composer submit actions, the payload includes text, attachments, options,
and any selected tools/skills/MCP entries exposed by the component. The action
owns persistence and timeline updates; the Composer does not automatically
persist or append messages.

For Form submit actions, validate the object keyed by the form component id.
Current clients include the form values both under the form id and, for
compatibility, as top-level fields. New module actions should use the form-id
object as the contract and ignore the top-level compatibility fields.

With `strip_extra=True`, undeclared client fields are removed from `ctx`, while
runtime keys added by the core, such as `_surface_id`, `stream_id`, and
`session_key`, are preserved.

For uploads with `ingest: true`, persist `extraction_request_id` from the
attachment payload when present. Do not reconstruct it by reading internal
knowledge tables.
