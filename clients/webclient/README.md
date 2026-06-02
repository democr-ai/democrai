# Democr.ai Web Client

React/Vite web client for the Democr.ai runtime.

## Setup

Install dependencies from the repository root:

```bash
yarn --cwd clients/webclient install
```

## Runtime configuration

Before running or serving the web client, configure:

```text
clients/webclient/public/env.js
```

The file is loaded by `index.html` and must define the HTTP and WebSocket endpoints of the Democr.ai core runtime:

```js
window.__CFG__ = {
  base_server_http_url: "http://localhost:8000",
  base_server_ws_url: "ws://localhost:8000/ws"
}
```

Use the host, port, and scheme that match your running core instance. For HTTPS deployments, the WebSocket URL should use `wss://`.

## Development

Start the core in server mode, then run the web client:

```bash
python main.py --mode server --host 127.0.0.1 --port 8000
yarn --cwd clients/webclient dev
```

## Build

```bash
yarn --cwd clients/webclient build
```
