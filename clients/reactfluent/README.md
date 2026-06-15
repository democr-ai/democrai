# Democrai React Client

React/Vite client that shares the Democrai client runtime, transport, state, routing, auth, and renderer contracts with the other web clients.

This client is a progressive desktop UI React client. Keep protocol-level code aligned with the other web clients; replace only visual renderers and local UI composition with the desktop design system.

## Development

```bash
npm install
npm run dev
npm run build
```

The default `public/env.js` points at the local core server:

```js
window.__CFG__ = {
  base_server_http_url: "http://localhost:8000",
  base_server_ws_url: "ws://localhost:8000/ws"
}
```

## Porting Notes

- Common runtime files should stay structurally aligned with the other web clients.
- The desktop theme is provided globally by `src/design/ClientRoot.tsx`.
- Renderer coverage should stay component-scoped; migrate forms, tables, panels, dialogs, tabs, and navigation in focused passes.
