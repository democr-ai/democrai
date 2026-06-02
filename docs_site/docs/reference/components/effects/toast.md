# Toast

[<- Back to Effects](./index.md)

`Toast` is a notification effect returned by an action. It displays a transient message; it is not mounted in the component tree.

## Payload

```python
sdk.effects.notify(
    "toast",
    {
        "title": "Saved",
        "text": "The record was saved.",
        "variant": "success",
        "duration": 2600,
    },
)
```

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Short notification title. |
| `text` | `str` | Body text. Web also accepts this as the main message text. |
| `variant` | `str` | Visual type. The test page uses `info`, `success`, `warning`, `error`, `danger`, and `default`. |
| `duration` | `int` | Display duration in milliseconds. |

## Trigger

<div class="docs-code-group" data-code-group>
  <div class="docs-code-group__tabs" role="tablist" aria-label="toast example 1">
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="toast-1-python" data-active="true" aria-selected="true">Python</button>
    <button class="docs-code-group__tab" type="button" role="tab" data-code-group-tab data-target="toast-1-yaml" aria-selected="false">YAML</button>
  </div>
  <div class="docs-code-group__panel" id="toast-1-python" data-code-group-panel data-active="true">
    <div class="language-python highlight"><pre><code>sdk.ui.Button(
    &quot;toast_success&quot;,
    &quot;Success&quot;,
    action=&quot;components.test_effect_toast&quot;,
    params={&quot;variant&quot;: &quot;success&quot;},
    variant=&quot;success&quot;,
    icon=&quot;ric.checkbox-circle-line&quot;,
)</code></pre></div>
  </div>
  <div class="docs-code-group__panel" id="toast-1-yaml" data-code-group-panel hidden>
    <div class="language-yaml highlight"><pre><code>- kind: Button
  id: toast_success
  label: Success
  action: components.test_effect_toast
  params: {variant: success}
  variant: success
  icon: ric.checkbox-circle-line</code></pre></div>
  </div>
</div>

## Action

```python
@action("test_effect_toast")
async def test_effect_toast(ctx: dict, session: dict, sdk) -> dict:
    variant = str(ctx.get("variant") or "info")
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": f"{variant.title()} toast",
                "text": f"Triggered with variant={variant}.",
                "variant": variant,
                "duration": 2600,
            },
        )
    )
```

## Behavior

- Web maps `success`, `error`/`danger`, `warning`, and `info` to Sonner toast types.
- Desktop displays `success`, `warning`, `error`/`destructive`, and the default informational style.
- `danger` is useful as an authoring alias for destructive actions; web maps it to an error toast.
