export type WsCodec = 'json' | 'deflate-json';

type EncodedFrame =
  | { kind: 'text'; payload: string }
  | { kind: 'bytes'; payload: Uint8Array };

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();

export function normalizeWsCodec(value: unknown, defaultCodec: WsCodec = 'json'): WsCodec {
  const raw = String(value ?? '').trim().toLowerCase();
  if (raw === 'deflate-json') return 'deflate-json';
  if (raw === 'json') return 'json';
  return defaultCodec;
}

async function compressDeflate(input: Uint8Array): Promise<Uint8Array> {
  if (typeof CompressionStream === 'undefined') {
    throw new Error('CompressionStream not supported');
  }

  const stream = new CompressionStream('deflate');
  const writer = stream.writable.getWriter();
  await writer.write(input);
  await writer.close();
  const output = await new Response(stream.readable).arrayBuffer();
  return new Uint8Array(output);
}

async function decompressDeflate(input: Uint8Array): Promise<Uint8Array> {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('DecompressionStream not supported');
  }

  const stream = new DecompressionStream('deflate');
  const writer = stream.writable.getWriter();
  await writer.write(input);
  await writer.close();
  const output = await new Response(stream.readable).arrayBuffer();
  return new Uint8Array(output);
}

export async function encodeWsMessage(payload: unknown, codec: WsCodec): Promise<EncodedFrame> {
  const serialized = JSON.stringify(payload);
  if (codec !== 'deflate-json') {
    return { kind: 'text', payload: serialized };
  }

  try {
    const compressed = await compressDeflate(textEncoder.encode(serialized));
    return { kind: 'bytes', payload: compressed };
  } catch {
    return { kind: 'text', payload: serialized };
  }
}

async function normalizeInboundData(data: unknown): Promise<{ text?: string; bytes?: Uint8Array }> {
  if (typeof data === 'string') return { text: data };
  if (data instanceof ArrayBuffer) return { bytes: new Uint8Array(data) };
  if (ArrayBuffer.isView(data)) {
    return { bytes: new Uint8Array(data.buffer, data.byteOffset, data.byteLength) };
  }
  if (data instanceof Blob) {
    return { bytes: new Uint8Array(await data.arrayBuffer()) };
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

  if (codec === 'deflate-json') {
    try {
      const inflated = await decompressDeflate(bytes);
      return JSON.parse(textDecoder.decode(inflated));
    } catch {
      return JSON.parse(textDecoder.decode(bytes));
    }
  }

  return JSON.parse(textDecoder.decode(bytes));
}
