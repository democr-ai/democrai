# Chat Module Integration

This step closes the module and checks that all runtime assets are discoverable.

## Discovery

Decorated actions, tools, and agents are discovered by the module loader. The
package `__init__.py` files can stay minimal:

```python
"""Chat module."""
```

Action names are module-scoped by the runtime. YAML calls them with the module
prefix:

```yaml
action:
  name: chat.submit_message
```

The current action files are:

```text
modules/chat/actions/
  attachments.py
  conversation.py
```

The current tool files are:

```text
modules/chat/tools/
  attachments.py
  components.py
  retrieval.py
  stats.py
  wait.py
```

The current agent files are:

```text
modules/chat/agents/
  component.py
  stats.py
  summary.py
  title.py
```

## Page Boundary

Pages are thin entrypoints:

- load YAML with `sdk.ui.load(...)`;
- load the requested module rows;
- compute small state objects;
- seed `builder.set_data(...)` and `builder.set_store(...)`;
- use limited runtime property assignment only for dynamic component state that
  is not practical as static YAML binding.

The current exceptions are `MessageList.messages`, `Composer.voice`,
thread-specific `send_action`, and thread-specific `on_load_more`.

## SDK Boundary

The chat module should stay inside public SDK contracts:

| Need | Boundary |
| --- | --- |
| Persist chat rows | Module SQLAlchemy models through SDK database helpers/model methods |
| Resolve media preview URL | `module_sdk.media.get_public_url(...)` |
| Read/delete knowledge projections | `module_sdk.knowledge.*` |
| Discover composer options | `module_sdk.ai.get_composer_options_for_capability(...)` |
| Resolve chat provider | `module_sdk.ai.get_provider_for_objective(...)` |
| Cancel generation | `module_sdk.ai.cancel_request(...)` |
| Publish live UI updates | `module_sdk.effects.publish_*` |
| Ask client for current UI state | `module_sdk.effects.ask_current_*` |
| Authorize actions/pages | `@permission_required(...)` and `rbac.json` |

Do not import `democrai.core`, client renderers, engine internals, or extractor
internals from the module.

## Final Module Shape

After these steps, the module includes:

```text
modules/chat/
  manifest.json
  rbac.json
  models.py
  migrations/
  actions/
  agents/
  locales/
  skills/chat_context/SKILL.md
  tools/
  ui/
  utils/actions/
  utils/ui/yaml/
```

`migrations/` is generated from `models.py`. Do not start by hand-writing
migrations before the model contract is clear.

## Completion Criteria

The module is complete when:

- the manifest is minimal and does not request direct access the SDK already owns;
- models inherit the module base and expose needed filters;
- RBAC exposes `chat.view` and `chat.write`;
- home and thread pages are YAML-first;
- sidebar data is bound through `/chat/thread_list/items`;
- thread list pagination, rename, and delete update the current surface;
- home submit creates a thread and navigates;
- thread submit streams and patches `MessageList` without rerendering the page;
- attachments persist `storage_path`, `file_id`, and `extraction_request_id`;
- document tools use knowledge SDK readers/search/cache methods;
- stats/component agents are available as focused subagents;
- summary/title agents are registered assets with narrow responsibilities;
- component tools persist validated A2UI output as timeline entries;
- attachment preview resolves media URLs through the SDK;
- `docs_site/docs_html` is generated only by the docs build step, not edited by hand.
