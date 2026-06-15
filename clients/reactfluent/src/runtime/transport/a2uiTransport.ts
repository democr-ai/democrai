import { decodeWsMessage, encodeWsMessage, type WsCodec } from '../../utils/wsCodec';

export type A2UITransportKind = 'auto' | 'websocket' | 'native-ipc';

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

type NativeIpcProvider = {
  name: string;
  connect: () => Promise<void>;
  send: (payload: any) => Promise<void>;
  disconnect: () => Promise<void>;
  onMessage: (handler: (payload: any) => void) => Promise<() => void>;
  onDisconnected: (handler: () => void) => Promise<() => void>;
  onError: (handler: (error: any) => void) => Promise<() => void>;
};

type ElectronIpcBridge = {
  connectIpc?: () => Promise<void>;
  sendIpc?: (payload: any) => Promise<void>;
  disconnectIpc?: () => Promise<void>;
  onIpcMessage?: (handler: (payload: any) => void) => () => void;
  onIpcDisconnected?: (handler: () => void) => () => void;
  onIpcError?: (handler: (error: any) => void) => () => void;
};

function tauriGlobal(): TauriGlobal | null {
  const value = (window as any).__TAURI__;
  return value && typeof value === 'object' ? value as TauriGlobal : null;
}

function electronBridge(): ElectronIpcBridge | null {
  const value = (window as any).democraiElectron;
  return value && typeof value === 'object' ? value as ElectronIpcBridge : null;
}

export function isNativeIpcTransportAvailable(): boolean {
  return Boolean(getNativeIpcProvider());
}

function getTauriIpcProvider(): NativeIpcProvider | null {
  const tauri = tauriGlobal();
  const invoke = tauri?.core?.invoke;
  const listen = tauri?.event?.listen;
  if (!invoke || !listen) return null;
  return {
    name: 'tauri',
    connect: () => invoke('connect_ipc'),
    send: (payload: any) => invoke('send_ipc', { payload }),
    disconnect: () => invoke('disconnect_ipc'),
    onMessage: async (handler) => listen<any>('democrai-ipc-message', (event) => handler(event.payload)),
    onDisconnected: async (handler) => listen<any>('democrai-ipc-disconnected', handler),
    onError: async (handler) => listen<any>('democrai-ipc-error', (event) => handler(event.payload)),
  };
}

function getElectronIpcProvider(): NativeIpcProvider | null {
  const bridge = electronBridge();
  if (!bridge?.connectIpc || !bridge?.sendIpc || !bridge?.disconnectIpc) return null;
  if (!bridge.onIpcMessage || !bridge.onIpcDisconnected || !bridge.onIpcError) return null;
  return {
    name: 'electron',
    connect: () => bridge.connectIpc!(),
    send: (payload: any) => bridge.sendIpc!(payload),
    disconnect: () => bridge.disconnectIpc!(),
    onMessage: async (handler) => bridge.onIpcMessage!(handler),
    onDisconnected: async (handler) => bridge.onIpcDisconnected!(handler),
    onError: async (handler) => bridge.onIpcError!(handler),
  };
}

function getNativeIpcProvider(): NativeIpcProvider | null {
  return getTauriIpcProvider() || getElectronIpcProvider();
}

function resolveTransportKind(kind: A2UITransportKind): Exclude<A2UITransportKind, 'auto'> {
  if (kind === 'native-ipc') return 'native-ipc';
  if (kind === 'websocket') return 'websocket';
  return isNativeIpcTransportAvailable() ? 'native-ipc' : 'websocket';
}

export function createA2UITransport(options: A2UITransportOptions): A2UITransport {
  const kind = resolveTransportKind(options.kind);
  return kind === 'native-ipc'
    ? createNativeIpcTransport(options)
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

function createNativeIpcTransport(options: A2UITransportOptions): A2UITransport {
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
      const provider = getNativeIpcProvider();
      if (!provider) {
        options.onError(new Error('Native IPC transport is not available'));
        options.onClose();
        return;
      }

      closed = false;
      connecting = true;
      options.debugLog?.('transport:native-ipc:connect', { provider: provider.name });

      void Promise.all([
        provider.onMessage((payload) => options.onMessage(payload)),
        provider.onDisconnected(closeFromBackend),
        provider.onError((error) => options.onError(error)),
      ])
        .then(([messageUnlisten, disconnectedUnlisten, errorUnlisten]) => {
          unlistenMessage = messageUnlisten;
          unlistenDisconnected = disconnectedUnlisten;
          unlistenError = errorUnlisten;
          return provider.connect();
        })
        .then(() => {
          if (closed) return;
          connecting = false;
          open = true;
          options.debugLog?.('transport:native-ipc:open');
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
      const provider = getNativeIpcProvider();
      if (!provider || !open) return false;
      void provider.send(payload).catch((error) => {
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
      const provider = getNativeIpcProvider();
      if (provider) void provider.disconnect().catch(() => undefined);
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
