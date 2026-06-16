export type WsCodec = 'json' | 'deflate-json';

type EncodedFrame =
  | { kind: 'text'; payload: string }
  | { kind: 'bytes'; payload: Uint8Array };

export function normalizeWsCodec(value: unknown, defaultCodec: WsCodec = 'json'): WsCodec {
  const raw = String(value ?? '').trim().toLowerCase();
  if (raw === 'deflate-json') return 'deflate-json';
  if (raw === 'json') return 'json';
  return defaultCodec;
}

export async function encodeWsMessage(payload: unknown, codec: WsCodec): Promise<EncodedFrame> {
  const serialized = JSON.stringify(payload);
  // Default to JSON for React Native as native compression streams are not available
  return { kind: 'text', payload: serialized };
}

async function normalizeInboundData(data: unknown): Promise<{ text?: string; bytes?: Uint8Array }> {
  if (typeof data === 'string') return { text: data };
  if (data instanceof ArrayBuffer) return { bytes: new Uint8Array(data) };
  // ArrayBuffer.isView is not always reliable in all RN environments, 
  // but we can check if it's a typed array
  if (data && typeof data === 'object' && 'buffer' in data && 'byteOffset' in data) {
    const view = data as any;
    return { bytes: new Uint8Array(view.buffer, view.byteOffset, view.byteLength) };
  }
  return {};
}

export async function decodeWsMessage(data: unknown, codec: WsCodec): Promise<any> {
  const normalized = await normalizeInboundData(data);
  if (normalized.text != null) {
    return JSON.parse(normalized.text);
  }

  const bytes = normalized.bytes;
  if (!bytes) {
    throw new Error('Unsupported websocket frame');
  }

  // React Native version: fallback to plain text decoding
  const text = new TextDecoder().decode(bytes);
  return JSON.parse(text);
}
