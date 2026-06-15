# Democrai React Fluent Client

React/Vite client that shares the Democrai A2UI runtime, transport, state, routing, auth, and renderer contracts with `webclient` and `reactbootstrap`.

This client is a progressive Fluent UI React port. Keep protocol-level code aligned with the other web clients; replace only visual renderers and local UI composition with Fluent UI.

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

- Common runtime files should stay structurally aligned with `reactbootstrap` and `webclient`.
- Fluent UI is provided globally by `src/fluent/FluentRoot.tsx`.
- Initial Fluent renderer coverage starts with `Button`; migrate forms, tables, panels, dialogs, tabs, and navigation in focused passes.
