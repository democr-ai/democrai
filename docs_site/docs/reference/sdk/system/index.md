# SDK Domain: `system`

## Overview

The `system` domain groups operational runtime helpers that do not belong to a specific business entity such as users, files, or AI calls.

This is the domain you reach for when your module needs to understand something about the current runtime itself:

- which modules are installed or active
- how many sessions are currently active
- how many authenticated users or clients are connected right now
- what the current CPU/RAM/GPU snapshot looks like
- whether setup mode is still enabled
- how to write module-scoped log lines

That makes `module_sdk.system` a domain about runtime operations and environment state, not about business data.

## Mental Model

The top-level facade exposes:

- `module_sdk.system.modules`
- `module_sdk.system.sessions`
- `module_sdk.system.connections`
- `module_sdk.system.metrics`
- `module_sdk.system.runtime_nodes`
- `module_sdk.system.notifications`
- `module_sdk.system.setup`

and also direct helper methods:

- `module_sdk.system.os_name()`
- `module_sdk.system.has_nvidia()`
- `module_sdk.system.gpu_info()`
- `module_sdk.system.temp_dir()`
- `module_sdk.system.is_dev()`
- `module_sdk.system.log(...)`

In practice, that means the domain mixes:

- read-only runtime inspection
- lightweight operational reporting
- notification-center integration
- one privileged setup finalization path

It is worth keeping those categories separate in your head, because `setup.finalize(...)` is a very different kind of API from `metrics.read()`.

## What This Domain Is For

Use `module_sdk.system` when your module needs to:

- render dashboards based on module availability or runtime metrics
- check whether setup mode is still active
- count active sessions for operational UI
- count live connected users or client connections without using persisted sessions
- list runtime nodes reported by the metrics publisher
- read core notification state for a notification-center view
- create temporary working files under the application data directory
- write log lines with a stable module prefix
- finalize setup from the actual setup flow

Do not use it as a generic “misc helpers” bucket. If the capability belongs to a more specific domain such as `models`, `media`, or `tasks`, that domain should stay the primary entry point.

This domain is not an observability write API. Modules can read audit and usage data through read-only core models, but telemetry and audit events are produced by core runtime instrumentation.

## Subsections

- Runtime Identity and Logging
- Modules
- Sessions and Metrics
- Setup Mode
