import { getJwt } from '@/state/authStore';

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
  scope_type?: string;
  owner_user_id?: number;
  organization_id?: number | null;
  uploaded_by?: number;
  uploader_access_level?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  extraction_request_id?: string | null;
  background_task_id?: string | null;
};

export type LocalAttachmentValue = {
  local_id: string;
  name: string;
  size: number;
  type: string;
  mime: string;
  preview_url: string;
  file?: File;
  path?: string;
  file_id?: string;
  storage_path?: string;
  ingest?: boolean;
};

function getCoreHttpBaseUrl(): string {
  const configured = String(window.__CFG__?.base_server_http_url || '').trim();
  if (configured) return configured.replace(/\/+$/, '');
  throw new Error('missing_base_server_http_url');
}

function getCurrentModule(): string {
  if (typeof window === 'undefined') return 'dashboard';
  const path = window.location.pathname || '';
  const segments = path.split('/').filter(Boolean);
  return segments[0] || 'dashboard';
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

export function inferActionName(action: any): string {
  if (typeof action === 'string') return action.trim();
  if (action && typeof action === 'object' && typeof action.name === 'string') {
    return action.name.trim();
  }
  return '';
}

export async function uploadBrowserFile(
  file: File,
  options: {
    moduleName: string;
    ingest?: boolean;
    actionName?: string;
  },
): Promise<UploadedFileRef> {
  const { moduleName, ingest = true, actionName = '' } = options;
  const formData = new FormData();
  formData.append('module_name', String(moduleName || '').trim() || getCurrentModule());
  formData.append('ingest', ingest ? 'true' : 'false');
  const normalizedActionName = String(actionName || '').trim();
  if (normalizedActionName) formData.append('action_name', normalizedActionName);
  formData.append('file', file);

  const headers: Record<string, string> = {};
  const jwt = getJwt();
  if (jwt) headers['X-JWT'] = jwt;

  const response = await fetch(`${getCoreHttpBaseUrl()}/media/uploads/raw`, {
    method: 'POST',
    body: formData,
    headers,
    credentials: 'include',
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(text || `Upload failed with status ${response.status}`);
  }

  const payload = await response.json();
  const contentType = String(payload?.content_type || '');
  const storagePath = String(payload?.storage_path || '');
  const originalFilename = String(payload?.original_filename || '');
  const storedFilename = String(payload?.stored_filename || '');
  const sizeBytes = Number(payload?.size_bytes || 0);
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

export async function uploadBrowserFiles(
  files: File[],
  options: {
    moduleName: string;
    ingest?: boolean;
    actionName?: string;
  },
): Promise<UploadedFileRef[]> {
  const { moduleName, ingest = true, actionName = '' } = options;
  return Promise.all(
    files.map((file) => uploadBrowserFile(file, { moduleName, ingest, actionName })),
  );
}

export function toLocalAttachmentValue(file: File): LocalAttachmentValue {
  const mime = String(file.type || 'application/octet-stream');
  return {
    local_id: typeof crypto?.randomUUID === 'function'
      ? crypto.randomUUID()
      : `local_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    name: String(file.name || 'file'),
    size: Number(file.size || 0),
    type: mime,
    mime,
    preview_url: URL.createObjectURL(file),
    file,
  };
}

export function sanitizeAttachmentEntriesForTransport(entries: any): any {
  if (!Array.isArray(entries)) return entries;
  return entries.map((entry) => {
    if (!entry || typeof entry !== 'object') return entry;
    const { file, ...rest } = entry as Record<string, any>;
    void file;
    return { ...rest };
  });
}

export async function materializeAttachmentUploads(
  entries: any,
  options: {
    moduleName: string;
    ingest?: boolean;
    actionName?: string;
  },
): Promise<UploadedFileRef[]> {
  const source = Array.isArray(entries) ? entries : [];
  const resolved: UploadedFileRef[] = [];
  const pendingEntries: Array<{ file: File; ingest: boolean }> = [];

  source.forEach((entry) => {
    if (!entry || typeof entry !== 'object') return;
    const storagePath = String(entry.storage_path || entry.path || '').trim();
    if (storagePath) {
      const contentType = String(entry.content_type || '');
      const sizeBytes = Number(entry.size_bytes || entry.size || 0);
      resolved.push({
        ...entry,
        name: String(entry.original_filename || entry.name || entry.stored_filename || 'file'),
        size: sizeBytes,
        type: contentType,
        mime: contentType,
        path: storagePath,
        file_id: String(entry.file_id || ''),
        storage_path: storagePath,
        content_type: contentType,
        size_bytes: sizeBytes,
      });
      return;
    }
    if (entry.file instanceof File) {
      pendingEntries.push({
        file: entry.file,
        ingest: options.ingest ?? entry.ingest !== false,
      });
    }
  });

  if (pendingEntries.length === 0) return resolved;
  const uploaded = await Promise.all(
    pendingEntries.map((entry) => uploadBrowserFile(entry.file, {
      moduleName: options.moduleName,
      ingest: entry.ingest,
      actionName: options.actionName,
    })),
  );
  return [...resolved, ...uploaded];
}
