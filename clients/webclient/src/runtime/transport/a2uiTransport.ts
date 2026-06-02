import { decodeWsMessage, encodeWsMessage, type WsCodec } from '../../utils/wsCodec';

export type A2UITransportKind = 'auto' | 'websocket' | 'tauri-ipc';

export type A2UITransportCallbacks = {
  onOpen: () => void;
  onMessage: (message: any) => void;
  onError: (error?: any) => void;
  onClose: () => void;
  debugLog?: (scope: string, ...args: any[]) => void;
};

export type A2UITransportOptions = A2UITransportCallbacks & {
  kind: A2UITransportKind;
  url: string;
  codec: WsCodec;
};

export type A2UITransport = {
  connect: () => void;
  send: (payload: any) => boolean;
  close: () => void;
  isOpen: () => boolean;
  isConnecting: () => boolean;
};

type TauriGlobal = {
  core?: {
    invoke?: (command: string, args?: Record<string, any>) => Promise<any>;
  };
  event?: {
    listen?: <T>(event: string, handler: (event: { payload: T }) => void) => Promise<() => void>;
  };
};

function tauriGlobal(): TauriGlobal | null {
  const value = (window as any).__TAURI__;
  return value && typeof value === 'object' ? value as TauriGlobal : null;
}

export function isTauriIpcTransportAvailable(): boolean {
  const tauri = tauriGlobal();
  return Boolean(tauri?.core?.invoke && tauri?.event?.listen);
}

function resolveTransportKind(kind: A2UITransportKind): Exclude<A2UITransportKind, 'auto'> {
  if (kind === 'tauri-ipc') return 'tauri-ipc';
  if (kind === 'websocket') return 'websocket';
  return isTauriIpcTransportAvailable() ? 'tauri-ipc' : 'websocket';
}

export function createA2UITransport(options: A2UITransportOptions): A2UITransport {
  const kind = resolveTransportKind(options.kind);
  return kind === 'tauri-ipc'
    ? createTauriIpcTransport(options)
    : createWebSocketTransport(options);
}

function createWebSocketTransport(options: A2UITransportOptions): A2UITransport {
  let ws: WebSocket | null = null;
  let sendChain: Promise<void> = Promise.resolve();

  return {
    connect() {
      options.debugLog?.('transport:ws:connect', { url: options.url, codec: options.codec });
      ws = new WebSocket(options.url);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        options.debugLog?.('transport:ws:open');
        options.onOpen();
      };

      ws.onmessage = async (event) => {
        try {
          const message = await decodeWsMessage(event.data, options.codec);
          options.onMessage(message);
        } catch (error) {
          console.error('[a2uiTransport] Unable to decode websocket message', error);
        }
      };

      ws.onerror = (error) => {
        options.debugLog?.('transport:ws:error', error);
        options.onError(error);
      };

      ws.onclose = () => {
        options.debugLog?.('transport:ws:close');
        options.onClose();
      };
    },
    send(payload: any) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      sendChain = sendChain
        .then(async () => {
          const encoded = await encodeWsMessage(payload, options.codec);
          if (!ws || ws.readyState !== WebSocket.OPEN) return;
          ws.send(encoded.payload);
        })
        .catch((error) => {
          console.error('[a2uiTransport] Unable to encode websocket message', error);
        });
      return true;
    },
    close() {
      ws?.close();
      ws = null;
    },
    isOpen() {
      return Boolean(ws && ws.readyState === WebSocket.OPEN);
    },
    isConnecting() {
      return Boolean(ws && ws.readyState === WebSocket.CONNECTING);
    },
  };
}

function createTauriIpcTransport(options: A2UITransportOptions): A2UITransport {
  let open = false;
  let connecting = false;
  let closed = false;
  let unlistenMessage: (() => void) | null = null;
  let unlistenDisconnected: (() => void) | null = null;
  let unlistenError: (() => void) | null = null;

  const cleanupListeners = () => {
    unlistenMessage?.();
    unlistenDisconnected?.();
    unlistenError?.();
    unlistenMessage = null;
    unlistenDisconnected = null;
    unlistenError = null;
  };

  const closeFromBackend = () => {
    if (closed) return;
    open = false;
    connecting = false;
    cleanupListeners();
    options.onClose();
  };

  return {
    connect() {
      const tauri = tauriGlobal();
      const invoke = tauri?.core?.invoke;
      const listen = tauri?.event?.listen;
      if (!invoke || !listen) {
        options.onError(new Error('Tauri IPC transport is not available'));
        options.onClose();
        return;
      }

      closed = false;
      connecting = true;
      options.debugLog?.('transport:tauri:connect');

      void Promise.all([
        listen<any>('democrai-ipc-message', (event) => options.onMessage(event.payload)),
        listen<any>('democrai-ipc-disconnected', closeFromBackend),
        listen<any>('democrai-ipc-error', (event) => options.onError(event.payload)),
      ])
        .then(([messageUnlisten, disconnectedUnlisten, errorUnlisten]) => {
          unlistenMessage = messageUnlisten;
          unlistenDisconnected = disconnectedUnlisten;
          unlistenError = errorUnlisten;
          return invoke('connect_ipc');
        })
        .then(() => {
          if (closed) return;
          connecting = false;
          open = true;
          options.debugLog?.('transport:tauri:open');
          options.onOpen();
        })
        .catch((error) => {
          connecting = false;
          open = false;
          cleanupListeners();
          options.onError(error);
          options.onClose();
        });
    },
    send(payload: any) {
      const invoke = tauriGlobal()?.core?.invoke;
      if (!invoke || !open) return false;
      void invoke('send_ipc', { payload }).catch((error) => {
        options.onError(error);
      });
      return true;
    },
    close() {
      const shouldNotifyClose = open || connecting;
      closed = true;
      open = false;
      connecting = false;
      cleanupListeners();
      const invoke = tauriGlobal()?.core?.invoke;
      if (invoke) void invoke('disconnect_ipc').catch(() => undefined);
      if (shouldNotifyClose) options.onClose();
    },
    isOpen() {
      return open;
    },
    isConnecting() {
      return connecting;
    },
  };
}
