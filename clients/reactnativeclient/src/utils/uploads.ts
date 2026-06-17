import { getCoreHttpBaseUrl } from './media';

export type UploadedFileRef = {
  id?: number;
  name: string;
  size: number;
  type: string;
  mime?: string;
  path: string;
  file_id: string;
  storage_path: string;
  module_name?: string;
  original_filename?: string;
  stored_filename?: string;
  content_type?: string;
  size_bytes?: number;
  sha256?: string;
};

function getCurrentModule(): string {
  return 'dashboard';
}

export function inferModuleNameFromAction(action: any): string {
  if (typeof action === 'string') {
    const value = action.trim();
    if (value.includes('.')) return value.split('.')[0] || getCurrentModule();
    return getCurrentModule();
  }
  if (action && typeof action === 'object' && typeof action.name === 'string') {
    return inferModuleNameFromAction(action.name);
  }
  return getCurrentModule();
}

function normalizeUploadedPayload(payload: any): UploadedFileRef {
  const contentType = String(payload?.content_type || payload?.mime || payload?.type || '');
  const storagePath = String(payload?.storage_path || payload?.path || '');
  const originalFilename = String(payload?.original_filename || payload?.name || '');
  const storedFilename = String(payload?.stored_filename || '');
  const sizeBytes = Number(payload?.size_bytes || payload?.size || 0);
  return {
    ...payload,
    id: payload?.id == null ? undefined : Number(payload.id),
    name: originalFilename || storedFilename || 'file',
    size: sizeBytes,
    type: contentType,
    mime: contentType,
    path: storagePath,
    file_id: String(payload?.file_id || ''),
    storage_path: storagePath,
    content_type: contentType,
    size_bytes: sizeBytes,
  };
}

export async function uploadNativeFile(
  entry: any,
  options: {
    moduleName: string;
    ingest?: boolean;
    jwt?: string;
    actionName?: string;
  },
): Promise<UploadedFileRef> {
  const uri = String(entry?.uri || entry?.url || '').trim();
  if (!uri) throw new Error('missing_upload_uri');

  const moduleName = String(options.moduleName || '').trim() || getCurrentModule();
  const mime = String(entry?.mimeType || entry?.mime || entry?.type || 'application/octet-stream');
  const name = String(entry?.name || entry?.fileName || `upload-${Date.now()}`);
  const formData = new FormData();
  formData.append('module_name', moduleName);
  formData.append('ingest', options.ingest === false ? 'false' : 'true');
  const normalizedActionName = String(options.actionName || '').trim();
  if (normalizedActionName) formData.append('action_name', normalizedActionName);
  formData.append('file', {
    uri,
    name,
    type: mime,
  } as any);

  const headers: Record<string, string> = {};
  if (options.jwt) headers['X-JWT'] = options.jwt;

  const response = await fetch(`${getCoreHttpBaseUrl()}/media/uploads/raw`, {
    method: 'POST',
    body: formData,
    headers,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || `Upload failed with status ${response.status}`);
  }

  return normalizeUploadedPayload(await response.json());
}

export async function materializeAttachmentUploads(
  entries: any,
  options: {
    moduleName: string;
    ingest?: boolean;
    jwt?: string;
    actionName?: string;
  },
): Promise<UploadedFileRef[]> {
  const source = Array.isArray(entries) ? entries : [];
  const resolved: UploadedFileRef[] = [];
  const pendingEntries: any[] = [];

  source.forEach((entry) => {
    if (!entry || typeof entry !== 'object') return;
    const storagePath = String(entry.storage_path || entry.path || '').trim();
    const uri = String(entry.uri || entry.url || '').trim();
    if (storagePath && !uri.startsWith('file:')) {
      resolved.push(normalizeUploadedPayload(entry));
      return;
    }
    if (uri) pendingEntries.push(entry);
  });

  if (pendingEntries.length === 0) return resolved;
  const uploaded = await Promise.all(
    pendingEntries.map((entry) => uploadNativeFile(entry, {
      moduleName: options.moduleName,
      ingest: options.ingest ?? entry.ingest !== false,
      jwt: options.jwt,
      actionName: options.actionName,
    })),
  );
  return [...resolved, ...uploaded];
}
