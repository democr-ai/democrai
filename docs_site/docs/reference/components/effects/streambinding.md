# StreamBinding

[<- Back to Effects](./index.md)

`StreamBinding` is an invisible runtime component. It subscribes the current client stream to a named runtime stream and converts matching events into client state updates.

Use it for live feeds that are not finite background jobs: runtime metrics, telemetry samples, live logs already modeled as stream events, or any bounded series that should update existing components through bindings.

Do not use it as a replacement for `BackgroundTask`. A `BackgroundTask` represents work with a lifecycle; `StreamBinding` represents a mounted subscription.

For module-owned continuous publishers, use a `long_run_command` to publish
events and let pages subscribe with `StreamBinding`. The command owns the
producer lifecycle; the page only decides how to map stream payloads into UI
state.

## Runtime Flow

1. The page renders a `StreamBinding`.
2. The client asks the core runtime to subscribe that binding.
3. The runtime listens to the configured source stream.
4. Matching events are transformed into `stateUpdate` messages for the client stream.
5. Components bound to that page/global store update normally.
6. When the component unmounts or the client disconnects, the runtime unsubscribes.

## Python Contract

```python
sdk.ui.StreamBinding(
    id: str,
    stream: str,
    event: str = "",
    target: dict | None = None,
    transformer: str | dict | None = None,
)
```

## Supported Properties

| Property | Type | Required | Python | YAML | Notes |
|---|---|---|---|---|---|
| `id` | `str` | yes | constructor | `id` | Stable binding id. |
| `stream` | `str` | yes | constructor | `stream` | Runtime stream to subscribe to. |
| `event` | `str` | no | constructor | `event` | Matches payload `event_name`. Empty means all events. |
| `target.store` | `page | global` | yes | `target` | `target.store` | Store scope to update. |
| `target.path` | `str` | yes | `target` | `target.path` | Base store path. |
| `target.mode` | `set | append_window` | no | `target` | `target.mode` | Update strategy. Default is `set`. |
| `target.window` | `int` | no | `target` | `target.window` | Maximum list length for `append_window`. |
| `target.mappings` | `dict[str, str]` | yes, unless `transformer` is used | `target` | `target.mappings` | Maps store fields to payload selectors. |
| `transformer` | `str | dict` | no | constructor | `transformer` | Action called for each matching payload before writing store values. |
| `transformer.name` | `str` | yes, when `transformer` is a dict | `transformer` | `transformer.name` | Qualified action name. |
| `transformer.context` | `dict` | no | `transformer` | `transformer.context` | Static configuration passed to the action. |

Selectors currently support direct payload fields with `$.field` or dotted object paths such as `$.node.cpu_percent`.

## Transformer Actions

Use `transformer` when the stream payload must be filtered, grouped, merged with
current client state, or converted into multiple store paths.

The transformer action receives:

| Context key | Value |
|---|---|
| `stream_id` / `_stream_id` | Current client stream id. Use it with `sdk.effects.ask_current_store_value(...)` when the transformer needs the current page/global store value. |
| `binding_id` | Mounted `StreamBinding` id. |
| `source_stream` | Runtime stream being consumed. |
| `event` | Matched event name. |
| `payload` | Raw stream event payload. |
| `target` | Declared `target` dictionary. |
| `context` | Static `transformer.context` dictionary. |

Return one of these shapes:

```python
return {"value": next_value}
```

`value` is written to `target.path`.

```python
return {
    "values": {
        "/path/one": value_one,
        "/path/two": value_two,
    }
}
```

`values` writes explicit store paths in the target scope.

## YAML Example

```yaml
- kind: StreamBinding
  id: gpu_usage_binding
  stream: system.runtime.metrics.events
  event: runtime.metrics.sample
  target:
    store: page
    path: /runtime_metrics/gpu
    mode: append_window
    window: 60
    mappings:
      data: $.vram_used_percent
      labels: $.timestamp

- kind: Chart
  id: gpu_usage_chart
  chart_type: line
  data: {type: store, scope: page, path: /runtime_metrics/gpu/data}
  labels: {type: store, scope: page, path: /runtime_metrics/gpu/labels}
```

## Runtime Metrics Example

The core runtime publishes node resource samples on:

```text
system.runtime.metrics.events
```

with `event_name`:

```text
runtime.metrics.sample
```

The sample payload includes `node_id`, `timestamp`, `label`, `cpu_percent`,
`ram_used_percent`, `ram_used_mb`, `ram_total_mb`, `vram_used_percent`,
`vram_used_mb`, `vram_total_mb`, and `has_nvidia_gpu`.

```yaml
- kind: StreamBinding
  id: node_vram_binding
  stream: system.runtime.metrics.events
  event: runtime.metrics.sample
  target:
    store: page
    path: /runtime_metrics/vram
    mode: append_window
    window: 60
    mappings:
      data: $.vram_used_percent
      labels: $.label
```

To group samples by node before writing the page store, use a transformer:

```yaml
- kind: StreamBinding
  id: node_metrics_binding
  stream: system.runtime.metrics.events
  event: runtime.metrics.sample
  transformer:
    name: monitor.transform_runtime_metrics
    context:
      window: 60
  target:
    store: page
    path: /runtime_metrics/by_node
```

The action can read the current client-side value and return the replacement:

```python
from democrai.sdk.decorators import action


@action("transform_runtime_metrics")
async def transform_runtime_metrics(ctx: dict, module_sdk):
    current = await module_sdk.effects.ask_current_store_value(
        ctx["stream_id"],
        ctx["target"]["path"],
        ctx["target"].get("store", "page"),
    )
    next_value = dict(current or {})
    next_value[ctx["payload"]["node_id"]] = ctx["payload"]
    return {"value": next_value}
```

## Module Publisher Example

A module can publish a long-running feed through a command registered at module
initialization:

```python
import asyncio
from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.decorators import long_run_command


@long_run_command("my_module.metrics_publisher")
async def metrics_publisher(stop_event=None):
    while stop_event is None or not stop_event.is_set():
        await sdk.effects.publish_to_stream(
            "my_module.metrics",
            {
                "event_name": "my_module.metrics.sample",
                "value": 42,
                "label": "sample",
            },
        )
        await asyncio.sleep(1)
```

The page subscribes without knowing how the producer is scheduled:

```yaml
- kind: StreamBinding
  id: my_module_metrics_binding
  stream: my_module.metrics
  event: my_module.metrics.sample
  target:
    store: page
    path: /my_module/metrics
    mode: append_window
    window: 60
    mappings:
      data: $.value
      labels: $.label

- kind: Chart
  id: my_module_metrics_chart
  chart_type: line
  data: {type: store, scope: page, path: /my_module/metrics/data}
  labels: {type: store, scope: page, path: /my_module/metrics/labels}
```

## Python Example

```python
builder.add(
    sdk.ui.StreamBinding(
        "gpu_usage_binding",
        stream="system.runtime.metrics.events",
        event="runtime.metrics.sample",
        target={
            "store": "page",
            "path": "/runtime_metrics/gpu",
            "mode": "append_window",
            "window": 60,
            "mappings": {
                "data": "$.vram_used_percent",
                "labels": "$.timestamp",
            },
        },
    )
)
```
