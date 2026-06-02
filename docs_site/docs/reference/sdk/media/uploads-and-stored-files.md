# Uploads and Stored Files

This page covers the storage side of the `media` contract:

- `add(...)`
- `add_model(...)`
- `add_model_from_source(...)`
- `view(...)`
- `get_path(...)`
- `move(...)`
- `delete(...)`

These methods are the ones a module author should use when dealing with persisted media assets.

## The Core Rule

When a file matters beyond the current request, your module should persist it through `module_sdk.media` and keep the resulting media path in its own state.

That means:

- do not keep `/tmp/...` paths in your database
- do not pass local filesystem paths around as if they were stable asset references
- do not make the UI reason about provider paths or local files

The module should keep one stable thing: the stored media path.

## `add(path, payload) -> str`

This is the write method.

Use it when your module has bytes and wants to persist them into media storage.

Example:

```python
report_path = module_sdk.media.add(
    "monthly-summary.pdf",
    pdf_bytes,
)
```

### What It Is For

Use `add(...)` for the normal module case:

- an export was generated
- a processed image was produced
- a document was normalized
- a binary artifact has to be kept for later

The important thing is that the file is now a persisted media asset, not just a transient file that happened to exist on disk once.

The path you pass here is only a filename or filename hint. The final storage path is computed by the runtime.

### Why Use It

This method keeps the write path simple.

The module provides the file name it wants to preserve, the media layer computes the canonical storage path, persists the bytes through the active provider, and returns the stored path your module can save in the database or pass to later flows.

That computed path includes the runtime scope information that matters operationally:

- module
- user
- organization when present
- date partition
- generated file id

### What It Validates

`add(...)` is intentionally strict:

- if `path` is empty, it raises `ValueError("path is required")`
- if `payload` is empty, it raises `ValueError("media payload is empty")`

That strictness is useful because it prevents “successful” writes of meaningless data.

## What The Returned Path Looks Like

The exact value depends on the current session, but the shape is intentionally scoped.

A typical stored path looks like:

```text
media/<module>/org_<organization>/uid_<user>/<yyyy>/<mm>/<dd>/<file_id>_<filename>
```

That is why the caller should persist the returned value, not try to predict it.

### Real Usage Pattern

Imagine a module that receives an uploaded PDF, extracts some pages, and stores the cleaned result:

```python
cleaned_path = module_sdk.media.add(
    "cleaned.pdf",
    cleaned_pdf_bytes,
)

module_sdk.database.update(
    ContractDocument,
    document_id,
    cleaned_media_path=cleaned_path,
)
```

That is the right kind of persistence flow for the SDK: the module keeps the resulting media path, not a local temp path and not a provider-specific URL.

## `add_model(model_id, *, payload=None, source_path=None, filename=None) -> str`

This is the shared model write method.

Use it when the artifact is not a normal user-scoped media file, but a model that must live in shared storage so that other nodes or runtimes can see it too.

Unlike `add(...)`, this method does not write under the module/user/organization tree. It always writes under:

```text
models/<id>/...
```

That distinction matters because model artifacts are runtime assets, not user uploads.

### What It Is For

Use `add_model(...)` when you need to persist:

- one model file
- one already-stored model artifact that must be copied into the shared model namespace
- one whole model directory

This is the SDK method for the case you described explicitly: model storage must be shared across multinode deployments and must not be partitioned by user.

### Supported Input Modes

The method supports three practical input forms:

1. raw bytes plus an explicit filename
2. a `source_path` pointing to a file
3. a `source_path` pointing to a directory

It also accepts storage-backed sources using the stored media path returned by
`add(...)` and copies them into the shared model namespace.

### Example: Save One Model File From Bytes

```python
model_path = module_sdk.media.add_model(
    "llama3-8b",
    payload=weights_bytes,
    filename="model.gguf",
)
```

The returned path is:

```text
models/llama3-8b/model.gguf
```

### Example: Save One Local Model Directory

```python
model_prefix = module_sdk.media.add_model(
    "mistral-7b-instruct",
    source_path="/tmp/exported-model",
)
```

If the source is a directory, the SDK writes the whole tree under:

```text
models/mistral-7b-instruct/...
```

and also writes a manifest file so the stored directory is explicit rather than implicit.

### Example: Copy An Already Stored Artifact Into Shared Model Storage

```python
shared_path = module_sdk.media.add_model(
    "qwen2.5",
    source_path=row.uploaded_media_path,
    filename="weights.safetensors",
)
```

This is useful when a module first receives an uploaded artifact through normal media flows, but the final canonical destination must be shared model storage.

### Validation Rules

`add_model(...)` is strict on purpose:

- if neither `payload` nor `source_path` is provided, it raises `ValueError("model source is required")`
- if both are provided, it raises `ValueError("provide either payload or source_path")`
- if bytes mode is used without `filename`, it raises `ValueError("filename is required when saving model bytes")`
- if the local source path is unreadable, it raises `ValueError("model source path is not readable")`

### Why This Method Exists Separately

It would be a mistake to overload `add(...)` with “sometimes user-scoped, sometimes shared model-scoped” behavior.

Keeping `add_model(...)` separate makes the storage intent obvious:

- `add(...)` is for normal module media, scoped by module and user
- `add_model(...)` is for shared model artifacts under `models/<id>/...`

## `add_model_from_source(model_id, *, source, filename=None, progress_callback=None) -> str`

This is the remote model import method.

Use it when the model source is remote and the final artifact must be persisted
under shared model storage.

The caller describes the source. The SDK handles the download mechanics,
temporary staging path, Hugging Face token handling, and final write through the
active media provider.

This method is part of the public `media` SDK because model provisioning flows
need one stable path for remote model materialization. It is not a general HTTP
download helper for arbitrary module data. Normal module files should still use
`add(...)`; already-local or already-uploaded model artifacts should use
`add_model(...)`.

Do not call provider download libraries such as `huggingface_hub.snapshot_download`
directly from modules or engines. Also do not call low-level HTTP helpers from
module or engine code just to assemble model files locally.

Large downloads are streamed to a temporary file. The SDK does not read whole
model shards into memory. When the active media provider supports direct file
persistence, the staged file is also copied or uploaded without loading the
whole file into memory.

### Hugging Face Snapshot Example

```python
storage_ref = module_sdk.media.add_model_from_source(
    "qwen3-tts-tokenizer-12hz",
    source={
        "type": "huggingface",
        "repo": "Qwen/Qwen3-TTS-Tokenizer-12Hz",
        "snapshot": True,
    },
)
```

The SDK reads `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` from the managed environment
when present and sends it explicitly. It does not rely on user-home credential
files such as `~/.netrc`.

The returned value is a media-provider storage reference, usually:

```text
models/qwen3-tts-tokenizer-12hz
```

### Hugging Face File Example

```python
storage_ref = module_sdk.media.add_model_from_source(
    "llama-3.2-1b-gguf",
    source={
        "type": "huggingface",
        "repo": "bartowski/Llama-3.2-1B-Instruct-GGUF",
        "files": ["Llama-3.2-1B-Instruct-Q4_K_M.gguf"],
    },
)
```

If exactly one Hugging Face file is provided and `snapshot` is not true, the SDK
stores it as one model file under:

```text
models/llama-3.2-1b-gguf/Llama-3.2-1B-Instruct-Q4_K_M.gguf
```

### URL File Example

```python
storage_ref = module_sdk.media.add_model_from_source(
    "custom-model",
    source={
        "type": "url",
        "url": "https://example.test/model.bin",
    },
    filename="model.bin",
)
```

### Supported Source Shapes

The supported source types are:

- `{"type": "huggingface", "repo": "...", "revision": "main", "files": [...], "snapshot": true}`
- `{"type": "url", "url": "..."}`

For Hugging Face sources:

- `repo` is required
- `revision` defaults to `main`
- `files` may be omitted when `snapshot` is true
- one file without `snapshot` is stored as a single model file
- snapshot sources are staged under the application temp directory and then
  persisted with `add_model(...)`

The final persistence path always goes through the active media provider.

### Progress Callback

`progress_callback` is optional. It is intended for long-running provisioning
flows that already run inside a background task.

The callback is synchronous and receives a dictionary shaped like:

```python
{
    "label": "model-00002-of-00004.safetensors",
    "downloaded_bytes": 2147483648,
    "total_bytes": 3998751275,
    "file_index": 2,
    "total_files": 4,
}
```

`total_bytes` may be `0` when the remote server does not provide a content
length. Callers should treat progress as advisory UI feedback, not as a source
of persisted model metadata.

When calling from async module code, bridge the callback back to the event loop
instead of awaiting inside it. A typical catalog/task flow does this by calling
`asyncio.run_coroutine_threadsafe(module_sdk.tasks.update_progress(...), loop)`
from the callback.

## `view(path) -> bytes`

This is the read method.

Use it when you already have a persisted media path and need the asset bytes again.

Example:

```python
payload = module_sdk.media.view(document.media_path)
```

### What It Is For

Typical cases:

- reading a stored PDF before sending it to a parser
- loading a generated CSV before attaching it to an email flow
- reopening a stored image before resizing it

The important distinction is that `view(...)` is for persisted assets. If your code still depends on a transient local file path from the upload phase, you have not finished normalizing the flow yet.

### Why Use It

The caller should not care whether storage is local, remote, or provider-backed in some other way. `view(...)` keeps the read path focused on the one thing the module actually needs: bytes.

### Accepted Path Form

`view(...)` accepts the stored media path returned by the SDK or runtime media
provider. Keep that storage path in backend state, and convert it to a public
URL only when rendering UI.

## `get_path(path, *, destination_dir=None) -> MaterializedMedia`

Use `get_path(...)` only when the next library needs a local filesystem path and cannot consume bytes from `view(...)`.

Example:

```python
materialized = module_sdk.media.get_path(model.storage_path)
try:
    run_path_only_library(materialized.path)
finally:
    materialized.cleanup()
```

The active media provider decides how to satisfy the request:

- local storage returns the existing path under the media root
- distributed storage downloads the file or directory into a temporary local path

The returned object exposes:

- `path`: local filesystem path
- `temporary`: whether the path is a temporary materialization
- `cleanup()`: releases temporary files when needed

Do not store the returned path in database rows. Store the media storage reference and call `get_path(...)` again when a path-only consumer needs it.

## `move(source_path, destination_path) -> str`

This is the rename or relocation method.

Use it when an asset already exists in storage and your module wants that same asset to live under a new path.

Example:

```python
final_path = module_sdk.media.move(
    "drafts/reports/run-42.pdf",
    "reports/2026/04/final-report.pdf",
)
```

### What It Is For

This is useful when the module workflow has clear stages:

- a draft becomes a final artifact
- a temporary namespace becomes a canonical namespace
- a user-owned path becomes an organization-owned path

The important thing is that the identity of the stored file changes at the storage-path level without forcing the module to manually read, re-add, and clean up the old object.

### What It Does

At runtime the method:

1. reads the source bytes
2. writes them to the destination
3. deletes the old object
4. updates the upload metadata row when one exists

That last detail matters because the module should not have to remember to keep media metadata aligned after a move.

### Why Use It

Without `move(...)`, modules tend to reimplement the same fragile sequence in slightly different ways. Centralizing it in the SDK keeps both the stored object and the tracked metadata aligned.

## `delete(path) -> None`

This is the removal method.

Use it when a persisted asset is no longer needed.

Example:

```python
module_sdk.media.delete(document.media_path)
```

### What It Is For

Typical cases:

- a user deletes an attachment
- a generated artifact is replaced and the old one should disappear
- a cleanup action removes obsolete exports

### What It Does

The method deletes:

- the stored object itself
- the matching upload metadata row when the path belongs to a tracked upload

That means the module does not need to remember two separate cleanup steps.

### Why Use It

If the module removes the application record but leaves the stored asset behind, media storage slowly accumulates junk. `delete(...)` is the explicit cleanup point for the asset itself.

## Practical End-To-End Example

A realistic module flow usually looks like this:

1. receive bytes from an upload or a generated artifact
2. persist them with `add(...)` or `add_model(...)` depending on whether the artifact is normal media or shared model storage
3. keep the returned media path in the module model
4. later reopen the asset with `view(...)`
5. if the asset changes namespace, use `move(...)`
6. if the asset is no longer needed, use `delete(...)`

Example:

```python
stored_path = module_sdk.media.add(
    "original.pdf",
    uploaded_bytes,
)

module_sdk.database.update(
    Invoice,
    invoice_id,
    original_media_path=stored_path,
)

payload = module_sdk.media.view(stored_path)
signed_payload = sign_invoice_pdf(payload)

signed_path = module_sdk.media.add(
    "signed.pdf",
    signed_payload,
)

module_sdk.database.update(
    Invoice,
    invoice_id,
    signed_media_path=signed_path,
)
```

That is the level of abstraction module authors should have: persist, read, move, delete. Not provider plumbing.
