const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, handler) {
  const listener = (_event, payload) => handler(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld('democraiElectron', {
  connectIpc: () => ipcRenderer.invoke('democrai:connect-ipc'),
  sendIpc: (payload) => ipcRenderer.invoke('democrai:send-ipc', payload),
  disconnectIpc: () => ipcRenderer.invoke('democrai:disconnect-ipc'),
  onIpcMessage: (handler) => subscribe('democrai-ipc-message', handler),
  onIpcDisconnected: (handler) => subscribe('democrai-ipc-disconnected', handler),
  onIpcError: (handler) => subscribe('democrai-ipc-error', handler),
});

