# Engine Runtime Media

This page covers the engine-worker media helpers exposed by:

```python
from democrai.sdk.engine_runtime_media import (
    media_exists,
    materialize_media,
    save_model_artifact,
)
```

These helpers are not part of `module_sdk.media`. They are a narrow runtime
surface for engine implementations that run inside the isolated engine worker.

## Boundary

Use this module only from engine runtime code.

The helpers require the engine worker parent channel. If they are called from a
module action, a normal Python shell, an install method, or any process that is
not an engine worker, they raise:

```text
engine_runtime_media_only_available_in_engine_worker
```

That restriction is intentional. Engine code should not import core internals or
request the application media provider directly. The engine worker asks its
parent process to perform storage operations and receives only the runtime-safe
result it needs.

## Why This Exists

Engine workers run under a sandbox. They may need to consume user-configured
media or persist generated model artifacts, but they must not reach into the
application storage layer directly.

The parent process owns the media provider. The engine worker owns model
execution.

`engine_runtime_media` is the bridge between those two responsibilities:

- the engine passes storage references
- the parent materializes or saves through the active media provider
- the engine receives paths inside its allowed runtime area
- model artifacts are written back under the canonical `models/...` namespace

This keeps local storage, S3-like providers, sandbox paths, and model artifact
placement centralized.

## `media_exists(storage_path: str) -> bool`

Return whether a storage path exists through the parent runtime.

Example:

```python
from democrai.sdk.engine_runtime_media import media_exists

if media_exists("models/qwen_tts_voice_clones_abcd/voice_clone_prompt.pt"):
    ...
```

Use it when an engine has a persisted artifact reference and needs to decide
whether to rebuild or reuse that artifact.

The method accepts storage paths, not local filesystem paths.

## `materialize_media(storage_path: str, destination_dir: str | None = None) -> RuntimeMaterializedMedia`

Materialize a stored media object to a local path that the engine worker can
read.

Example:

```python
from democrai.sdk.engine_runtime_media import materialize_media

materialized = materialize_media(
    "media/system/uid_1/2026/05/14/reference.wav"
)
try:
    engine.load_reference_audio(materialized.path)
finally:
    materialized.cleanup()
```

When `destination_dir` is omitted, the parent materializes the file inside the
current engine runtime temporary directory. That matters because media storage
paths can point outside the worker sandbox. The worker should use the returned
path, not reconstruct the provider path itself.

The return value is a `RuntimeMaterializedMedia` object:

```python
RuntimeMaterializedMedia(
    path="/runtime/readable/path/reference.wav",
    temporary=True,
)
```

Call `cleanup()` when the path is no longer needed. Cleanup is a no-op for
non-temporary materializations and removes temporary files or directories when
the parent provider created a copy.

## `save_model_artifact(storage_path: str, source_path: str) -> str`

Save a local file produced by the engine under model storage.

Example:

```python
from democrai.sdk.engine_runtime_media import save_model_artifact

saved_path = save_model_artifact(
    "models/qwen_tts_voice_clones_abcd/voice_clone_prompt.pt",
    "/tmp/voice_clone_prompt.pt",
)
```

The target path must be under `models/...`.

Use this for generated artifacts that belong with model storage, such as:

- voice clone prompts
- tokenizer side artifacts
- derived indexes
- compiled model fragments that should survive worker restart

Do not use it for ordinary generated output that belongs in user media. For
module-facing generated audio, images, or documents, return bytes to the runtime
or use the module-facing `module_sdk.media` contract at the module boundary.

## Voice Clone Pattern

A typical engine-side voice clone flow looks like this:

```python
from democrai.sdk.engine_runtime_media import (
    materialize_media,
    media_exists,
    save_model_artifact,
)

artifact_path = "models/qwen_tts_voice_clones_abcd/voice_clone_prompt.pt"

if media_exists(artifact_path):
    prompt = load_prompt(materialize_media(artifact_path))
else:
    reference = materialize_media(config["voice_clone_ref_audio_storage_path"])
    try:
        prompt = build_voice_clone_prompt(reference.path, config["voice_clone_ref_text"])
    finally:
        reference.cleanup()

    tmp_path = write_prompt_to_temp_file(prompt)
    save_model_artifact(artifact_path, tmp_path)
```

The source audio remains a normal media upload. The generated clone artifact is
what belongs in `models/...`.

## What Not To Do

Engine runtime code should not:

- import `democrai.core.runtime.foundation.app`
- call `app_ctx().media`
- call `module_sdk.media`
- build paths under the configured media storage root manually
- pass raw storage provider paths to model libraries
- save model artifacts under `media/system/...`

Those shortcuts bypass the runtime boundary and usually fail under sandboxed
execution.
