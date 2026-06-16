export {};

declare global {
  interface Window {
    __CFG__: {
      base_server_http_url: string;
      base_server_ws_url: string;
    };
    democraiElectron?: {
      connectIpc: () => Promise<void>;
      sendIpc: (payload: unknown) => Promise<void>;
      disconnectIpc: () => Promise<void>;
      onIpcMessage: (handler: (payload: unknown) => void) => () => void;
      onIpcDisconnected: (handler: () => void) => () => void;
      onIpcError: (handler: (error: unknown) => void) => () => void;
    };
  }
}
