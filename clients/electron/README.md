# Democrai Electron wrapper

Generic Electron desktop wrapper for Democrai web clients.

The application runner starts the selected web client dev server and then starts
this Electron shell. The web bundle selects the `native-ipc` A2UI transport
through `VITE_A2UI_TRANSPORT=native-ipc`.

The preload exposes a narrow `window.democraiElectron` bridge. The Electron main
process talks to the existing Democrai desktop socket using newline-delimited
JSON, matching the Tauri and Qt desktop protocols.

## Development

Install dependencies once:

```bash
yarn --cwd clients/electron install
```

Run from the repository root:

```bash
python main.py --client electron
```

Use a different web client with the existing web-client selector:

```bash
python main.py --client electron --tauri-web-client reactbootstrap
```

## Build

Build the web client first, then package Electron:

```bash
yarn --cwd clients/webclient build
yarn --cwd clients/electron build
```

Set `DEMOCRAI_ELECTRON_WEB_DIST` to load a different built web client directory.
