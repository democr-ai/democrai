# AI Composer

[<- Back to AI Chat](./index.md)

This page covers the write side of a chat UI. `Composer` collects user input and emits action payloads; it does not own message persistence or mutate the message timeline by itself.

## Rooted YAML Example

```yaml
- kind: Column
  id: support_chat
  children:
    - kind: ScrollArea
      id: support_messages_scroll
      scroll_y: true
      scroll_x: false
      children:
        - kind: MessageList
          id: support_messages
          messages: []
    - kind: Composer
      id: support_composer
      placeholder: Write a message...
      send_action:
        name: support.send_message
        context: {target: support_messages}
      cancel_action:
        name: support.stop_generation
        context: {}
      models: "@state/page/support/composer/models"
      model: "@state/page/support/composer/model"
      enable_attachment: true
      attachment_multiple: true
      attachment_accept: "@state/page/support/composer/attachment_accept"
      voice: true
      voice_action:
        name: composer_transcribe_audio
      model_capabilities: "@state/page/support/composer/model_capabilities"
      options: "@state/page/support/composer/options"
      options_schema: "@state/page/support/composer/options_schema"
      options_editable: "@state/page/support/composer/options_editable"
      capabilities:
        - value.set
        - disabled.set
      stop_enabled: true
```

## Parameters

| Property | Web | Desktop | Runtime update | Notes |
|---|---|---|---|---|
| `id` | yes | yes | no | Required |
| `placeholder` | yes | yes | yes | Supported |
| `value` | yes | yes | yes | Controlled input value |
| `disabled` | yes | yes | yes | Supported |
| `multiline` | yes | yes | structural | Do not rely on frequent live toggles |
| `send_action` | yes | yes | render-time | Submit action |
| `cancel_action` | yes | yes | render-time | Stop action |
| `action` | yes | yes | render-time | Generic interaction action |
| `on_submit` | yes | yes | render-time | Preferred explicit submit action |
| `on_stop_enabled` | yes | yes | render-time | Stop action |
| `stop_enabled` | yes | yes | render-time | Shows stop button |
| `voice` | yes | yes | render-time | Microphone toggle |
| `voice_action` | yes | yes | render-time | Action used to transcribe recorded audio |
| `enable_attachment` | yes | yes | render-time | Enables file attach UI |
| `attachment_multiple` | yes | yes | render-time | Allows multiple selected attachments |
| `attachment_accept` | yes | yes | render-time | MIME/file accept string supplied by the application |
| `ingest` | yes | yes | render-time | Defaults to `true`; set `false` to skip knowledge extraction enqueue for uploaded attachments |
| `models` | yes | yes | partial | Available model list |
| `model` | yes | yes | yes | Selected model |
| `tools` | yes | yes | render-time | Tool menu |
| `skills` | yes | yes | render-time | Skill menu |
| `model_capabilities` | yes | yes | yes | Model capability badges from SDK/model configuration |
| `show_capabilities` | yes | yes | yes | Shows or hides model capability badges |
| `options` | yes | yes | yes | Composer option values from SDK/model configuration |
| `options_schema` | yes | yes | yes | Editable composer option schema from SDK/model configuration |
| `options_editable` | yes | yes | yes | Enables composer option controls |
| `capabilities` | yes | yes | yes | Renderer update capabilities such as `value.set` |
| `active_capabilities` | yes | yes | yes | Current active runtime capability badges |
| `selected_tools` | yes | yes | initial state | Optional pre-selected tools |
| `selected_skills` | yes | yes | initial state | Optional pre-selected skills |
| `style` | yes | yes | yes | Standard styling |

## Placement

Place the composer outside the message `ScrollArea`, usually at the bottom of the chat column.
The message list can scroll independently while the composer remains reachable.

```yaml
- kind: Column
  id: support_chat
  children:
    - kind: ScrollArea
      id: support_messages_scroll
      scroll_y: true
      children:
        - kind: MessageList
          id: support_messages
          messages: []
    - kind: Composer
      id: support_composer
      placeholder: Write a message...
      send_action:
        name: support.send_message
        context: {target: support_messages}
```

## Model Options

Do not derive composer options by parsing model rows in module code. Use the SDK
AI helpers and pass the returned values to the composer through YAML bindings.

```python
composer_options = module_sdk.ai.get_composer_options_for_capability("chat")

builder.set_store(
    "/support/composer/model_capabilities",
    composer_options["model_capabilities"],
    scope="page",
)
builder.set_store(
    "/support/composer/options",
    composer_options["options"],
    scope="page",
)
builder.set_store(
    "/support/composer/options_schema",
    composer_options["options_schema"],
    scope="page",
)
builder.set_store(
    "/support/composer/options_editable",
    composer_options["options_editable"],
    scope="page",
)
```

Use `get_composer_options_by_model_registry_id(...)` when the page is tied to a
specific configured model.

## Runtime Updates

```python
return sdk.effects.respond(
    sdk.effects.ui_property_update("support_composer", "value", ""),
    sdk.effects.ui_property_update(
        "support_composer",
        "options",
        updated_options,
    ),
)
```

The composer emits interaction payloads such as:

- `intent="submit"`
- `intent="stop"`
- `intent="model_change"`
- `intent="tools_change"`
- `intent="skills_change"`
- `intent="voice_toggle"`
- `intent="attachment_add"`
- `intent="attachment_remove"`

Submit actions should usually:

1. persist the user message or enqueue it in backend state;
2. return a runtime patch for the visible message window, such as `messages.append`;
3. clear or update the composer with a direct property update.

Uploaded attachments are included in the action payload. The application action decides how to handle them. `ingest=false` only disables automatic knowledge extraction enqueue for uploaded attachments; it does not define the application-level attachment workflow.
