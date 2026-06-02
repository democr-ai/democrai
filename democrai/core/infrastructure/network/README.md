# Network Infrastructure

This package owns the runtime bus, streams, protocol handling, HTTP/WebSocket
surface and media proxy. It connects core and clients without making core
depend on a specific client implementation.

## Modes

`server` mode:

- exposes the full HTTP/WebSocket runtime.
- may be paired with a web client started by the runner.

`desktop` mode:

- is oriented around the desktop client transport.
- without `--http`, HTTP is limited to the surface needed by the media proxy.
- with `--http`, it also exposes the full HTTP/WebSocket runtime.

The runner chooses the client. Core network owns only the runtime transport.

## Key Files

- `runtime/network.py`: `Network` wiring and flow composition.
- `runtime/lifecycle.py`: start/stop and HTTP/WebSocket initialization.
- `contracts/`: bus and stream contracts.
- `providers/`: concrete network providers.
- `protocol/`: dispatcher and message handlers.
- `flows/`: request launch, stream, media and compatibility flows.
- `http/`: HTTP app, routes, auth and WebSocket handling.
- `factory/`: provider construction.
- `registry/`: registered clients and connections.
- `policy_guard.py`: Python-level network access guard.

## Streams and Progress

Streams are the right channel for transient events and frequent progress. The
database should receive meaningful state changes, not every output line or
download tick.

Pattern:

- frequent progress -> stream/runtime event.
- task phase change -> persisted state.
- completion/error -> persisted state and notification.

## Media Proxy

The media proxy resolves and streams authorized media. In desktop mode it may be
the only active HTTP surface when `--http` is not passed.

Media requests must preserve subject, session and access policy context.

## Rules

- Core network does not import clients.
- Transient streams do not become database state by default.
- Every message must carry coherent session/context.
- Media and network access go through policy guards and approvals.
- Desktop and server modes differ in exposed transport, not core contracts.
