# Democrai Tauri wrapper

Generic desktop wrapper for the React web client in `clients/webclient`.

The application runner starts the selected React dev server and then starts this
Tauri shell. The web bundle selects the `native-ipc` A2UI transport through
`VITE_A2UI_TRANSPORT=native-ipc`.

The IPC bridge talks to the existing Democrai desktop socket using newline
delimited JSON, matching the Qt desktop client protocol.
