# libmagic Bundle Layout

Place platform-specific `libmagic` runtime files in these folders so Nuitka can bundle them:

- `democrai/third_party/libmagic/linux/`
  - `libmagic.so` or `libmagic.so.1`
  - `magic.mgc`
- `democrai/third_party/libmagic/macos/`
  - `libmagic.dylib` (or compatible name)
  - `magic.mgc`
- `democrai/third_party/libmagic/windows/`
  - `magic1.dll` (or `libmagic-1.dll`)
  - `magic.mgc`

The bundle is considered valid only when the platform folder contains:

- `magic.mgc`
- at least one matching `libmagic` runtime library for that platform

If the folder exists but is empty or incomplete, the build script ignores it and falls back to autodiscovery on the current build machine.

At runtime the app tries to initialize MIME detection in this order:

1. `python-magic` (`libmagic`) using bundled files (if present)
2. `filetype`
3. filename-based fallback (`mimetypes`)

If bundled `libmagic` assets are missing or fail to load, the app falls back automatically.
