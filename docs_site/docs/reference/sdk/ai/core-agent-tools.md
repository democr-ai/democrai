# AI: Core Agent Tools

Core agent tools are runtime tools provided by Democr.ai itself. They are not
owned by a module, but modules and agents can use them by name when they build
provider options or declare agent capabilities.

Core tools are registered in the same agent tool registry as module tools. This
keeps tool execution uniform: the model sees a JSON-schema tool definition, the
runtime executes the registered callable, and the tool result is fed back into
the tool-call loop.

Both tools documented here are internal runtime tools and are registered with
`user_selectable=False`. They are not meant to appear as generic composer
options for end users.

## `core.run-skill-script`

`core.run-skill-script` executes a Python script exposed by an activated skill.

Modules usually do not add this tool manually. When provider options include
`skills`, the AI pipeline prepares the selected skill context and can expose
`core.run-skill-script` when script execution is needed.

Input schema:

```json
{
  "type": "object",
  "properties": {
    "skill": {
      "type": "string",
      "description": "Fully qualified skill name."
    },
    "script": {
      "type": "string",
      "description": "Script path relative to the skill scripts directory."
    },
    "args": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Command line arguments for the script."
    },
    "timeout_seconds": {
      "type": "number",
      "description": "Execution timeout in seconds."
    }
  },
  "required": ["skill", "script"]
}
```

Use this only for scripts that are part of a registered skill and expected by
that skill contract. Business persistence still belongs in actions and tools,
not in hidden skill scripts.

## `core.ask-user`

`core.ask-user` asks the current interactive user for structured input through
the runtime prompt system.

Use it when an agent cannot safely continue without a value that should come
from the user. The tool opens a user-facing form, waits for the response, and
returns the submitted data to the agent.

Input schema:

```json
{
  "type": "object",
  "properties": {
    "question": {
      "type": "string",
      "description": "Question shown above the form."
    },
    "form_model": {
      "type": "array",
      "description": "Flat list of form fields.",
      "items": {
        "type": "object",
        "properties": {
          "type": { "type": "string" },
          "name": { "type": "string" },
          "label": { "type": "string" },
          "placeholder": { "type": "string" },
          "options": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "label": { "type": "string" },
                "value": {}
              },
              "required": ["label", "value"]
            }
          },
          "multiple": { "type": "boolean" }
        },
        "required": ["type", "name"],
        "additionalProperties": true
      }
    },
    "values": {
      "type": "object",
      "description": "Initial form values keyed by field name."
    },
    "submit_label": {
      "type": "string",
      "description": "Submit button label."
    },
    "timeout_seconds": {
      "type": "number",
      "description": "How long to wait for the user response."
    }
  },
  "required": ["question", "form_model"]
}
```

The current implementation accepts a flat `form_model`. Do not use layout nodes
such as `row`, `column`, or nested `children` in the form model.

Supported field types:

| Type | Notes |
| --- | --- |
| `text`, `email`, `password` | Single-line text input. |
| `number`, `integer`, `int`, `float`, `decimal` | Numeric input. |
| `textarea` | Multi-line text. |
| `checkbox`, `check` | Boolean input. |
| `toggle`, `switch` | Boolean switch-style input. |
| `select` | Dropdown-style choice. Requires `options`. |
| `radio`, `radio_group` | Radio choice. Requires `options`. |
| `date`, `datetime`, `date_time` | Date or date-time input. |
| `file`, `attachment` | File input when supported by the client. |
| `audio_recorder` | Audio recording input when supported by the client. |
| `tags`, `tags_input` | Tag list input. |
| `editable_list` | Editable list input. |

For dropdown controls, use `type: "select"` with an `options` array. The
runtime does not accept `dropdown` as a form field type.

Example:

```python
result = await module_sdk.ai.run_tool(
    "core.ask-user",
    arguments={
        "question": "Which customer segment should be used?",
        "form_model": [
            {
                "type": "select",
                "name": "segment",
                "label": "Customer segment",
                "options": [
                    {"label": "Enterprise", "value": "enterprise"},
                    {"label": "SMB", "value": "smb"},
                ],
            },
            {
                "type": "textarea",
                "name": "notes",
                "label": "Notes",
            },
        ],
        "submit_label": "Continue",
        "timeout_seconds": 60,
    },
    context={"source": "reports.segment-selection"},
)
```

The returned payload includes the selected action and submitted form data. If
the user cancels or the prompt cannot be shown, the tool returns an error-shaped
payload instead of inventing values.

## Using Core Tools In Provider Options

Custom orchestration can pass core tool names next to module tool names:

```python
options = {
    "tools": [
        "reports.search-reports",
        "core.ask-user",
    ],
    "skills": ["reports.report_context"],
    "tool_max_iterations": 6,
}
```

The runtime resolves all selected tools through the same registry. Module tools
run in their module context. Core tools run in the core runtime context.

