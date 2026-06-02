# Public URLs and UI Consumption

This page covers the UI-facing side of the new `media` contract:

- `get_public_url(...)`

Even though it is only one method, it is one of the most important pieces of the entire domain because it defines how media reaches the client.

## `get_public_url(path) -> str | None`

This method returns the HTTP URL that the UI should actually consume.

Example:

```python
image_url = module_sdk.media.get_public_url("assets/hero.png")
```

Or for a persisted media path:

```python
preview_url = module_sdk.media.get_public_url(document.media_path)
```

### What It Is For

Use `get_public_url(...)` whenever a component needs an image URL, audio URL, video URL, PDF URL, or attachment URL.

This is the method you should use before passing a value to components such as:

- `Image`
- `Audio`
- `Video`
- `PdfViewer`
- attachment preview components

### Why It Exists

The module should not decide:

- whether a path is local or distributed
- whether the source is already internal or originally external
- whether the final client URL should be proxied
- how the current module name should be attached

All of that belongs to the runtime, not to every individual module author.

`get_public_url(...)` exists so the module can say only one thing:

“this is the media I want to show”.

The runtime then turns that into the correct HTTP URL for the current client flow.

## The Important Rule

The UI should consume the URL returned by `get_public_url(...)`, not the storage path and not the local file path.

That rule matters because the runtime wants media to pass through the HTTP layer, where it can apply:

- access checks
- proxy behavior
- client-safe URL normalization
- future policy changes in one central place

If a module bypasses that and gives the UI some other raw path, the module is leaking transport and storage concerns into places that should not know about them.

## What It Accepts

In practice `get_public_url(...)` is the method that absorbs the messy edge cases so the rest of the module code can stay simple.

It can be used with:

- stored media paths
- module assets such as `assets/...`
- sources that already resolve to runtime media URLs
- external URLs that the runtime must proxy

The point is not that the module author should memorize every branch. The point is the opposite: the module author should not need to.

## Real Example: Module Asset In A Component

If a module ships a static image under `assets/logo.png`, the right pattern is:

```python
builder.add(
    module_sdk.ui.Image(
        "module_logo",
        alt="Module logo",
        url=module_sdk.media.get_public_url("assets/logo.png"),
    )
)
```

This keeps the component code transport-agnostic. The module is not hardcoding `/media/modules/...`, and it is not assuming anything about where that asset ultimately lives.

## Real Example: Persisted Media In A Preview

If your module stored a generated report and later wants to show it:

```python
report_url = module_sdk.media.get_public_url(row.report_media_path)

builder.add(
    module_sdk.ui.PdfViewer(
        "report_preview",
        name="Generated report",
        url=report_url,
        height=520,
    )
)
```

This is the important distinction:

- the database stores the media path
- the UI receives the public URL

Those are not the same thing, and merging them leads to broken flows.

## What It Returns

If `path` is empty, the method returns `None`.

Otherwise it returns the runtime URL that the client should render. In the
current architecture that means a proxied `/media/proxy?...` URL produced by the
runtime.

The important point is not the exact current shape of the URL. The important point is that the module should treat it as a ready-to-render client URL.

## Why This Method Is Better Than Manual URL Construction

Without this method, modules quickly start doing the wrong things:

- hand-building `/media/modules/...`
- passing provider paths directly to components
- passing `/tmp/...` paths to the client
- special-casing external URLs in every feature module

That creates inconsistent behavior and weakens access control.

With `get_public_url(...)`, every module can follow the same rule:

- persist media with `add(...)`
- store the media path
- convert it to a client URL only at the UI boundary with `get_public_url(...)`

## Practical Guidance

The simplest stable pattern is:

1. keep stored paths in your backend state
2. call `get_public_url(...)` only when building UI or response payloads for clients
3. pass the returned value directly to the component

That separation keeps storage concerns and UI concerns from drifting into each other.
