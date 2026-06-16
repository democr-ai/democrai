const ABSOLUTE_URL_RE = /^https?:\/\//i;
const MEDIA_PREFIX_RE = /^\/?media\//i;
const DIRECT_MEDIA_PREFIXES = ['data:', 'blob:'] as const;
const DIRECT_MEDIA_TOKENS = ['ric.', '<svg'] as const;

export const DEFAULT_HTTP_BASE_URL = 'http://localhost:8000';

export function getCoreHttpBaseUrl(): string {
  return DEFAULT_HTTP_BASE_URL;
}

function encodePath(path: string): string {
  return path
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

function getCurrentModule(fallbackModuleName = 'dashboard'): string {
  return fallbackModuleName || 'dashboard';
}

function mediaProxyUrl(target: string, moduleName = getCurrentModule()): string {
  const query = new URLSearchParams({
    module_name: moduleName || 'dashboard',
    url: target,
  });
  return `${getCoreHttpBaseUrl()}/media/proxy?${query.toString()}`;
}

function isProxyMediaUrl(source: string): boolean {
  if (source.startsWith('/media/proxy') || source.startsWith('media/proxy')) return true;
  try {
    return new URL(source, getCoreHttpBaseUrl()).pathname === '/media/proxy';
  } catch {
    return false;
  }
}

function isStaticAsset(source: string): boolean {
  return /\.(svg|png|jpe?g|gif|webp|ico)$/i.test(source);
}

function resolvePassthroughSource(source: string): string | null {
  if (DIRECT_MEDIA_PREFIXES.some((prefix) => source.startsWith(prefix))) return source;
  if (DIRECT_MEDIA_TOKENS.some((prefix) => source.startsWith(prefix))) return source;
  return null;
}

function mediaTargetFromUrl(source: string): string {
  try {
    const parsed = new URL(source, getCoreHttpBaseUrl());
    if (parsed.pathname.startsWith('/media/')) {
      return `${parsed.pathname}${parsed.search}`;
    }
  } catch {
    return source;
  }
  return source;
}

function resolveRemoteSource(source: string, moduleName: string): string | null {
  if (!ABSOLUTE_URL_RE.test(source)) return null;
  if (isProxyMediaUrl(source)) return source;
  try {
    const parsed = new URL(source);
    if (parsed.pathname.startsWith('/media/')) {
      return mediaProxyUrl(mediaTargetFromUrl(source), moduleName);
    }
    return source;
  } catch {
    return source;
  }
}

function resolveEngineAssetSource(normalized: string, moduleName: string): string | null {
  const match = normalized.match(/^engines\/([^/]+)\/(.+)$/i);
  if (!match) return null;
  const [, engineId, filePath] = match;
  return mediaProxyUrl(`/media/engine/${encodeURIComponent(engineId)}/${encodePath(filePath)}`, moduleName);
}

function resolveExtractorAssetSource(normalized: string, moduleName: string): string | null {
  const match = normalized.match(/^extractors\/([^/]+)\/(.+)$/i);
  if (!match) return null;
  const [, extractorId, filePath] = match;
  return mediaProxyUrl(`/media/extractors/${encodeURIComponent(extractorId)}/${encodePath(filePath)}`, moduleName);
}

function resolveUploadStoragePathSource(normalized: string, moduleName: string): string | null {
  if (!normalized.startsWith('media/')) return null;
  const query = new URLSearchParams({ storage_path: normalized });
  return mediaProxyUrl(`/media/uploads/by-storage-path?${query.toString()}`, moduleName);
}

function resolveExplicitModuleAssetSource(normalized: string, moduleName: string): string | null {
  const absLocalModuleMatch = normalized.match(/\/application\/modules\/([^/]+)\/(.+)$/i);
  if (absLocalModuleMatch) {
    const [, explicitModuleName, filePath] = absLocalModuleMatch;
    return mediaProxyUrl(`/media/modules/${encodeURIComponent(explicitModuleName)}/${encodePath(filePath)}`, moduleName);
  }

  const absModuleMatch = normalized.match(/(?:^|\/)modules\/([^/]+)\/(.+)$/i);
  if (absModuleMatch) {
    const [, explicitModuleName, filePath] = absModuleMatch;
    return mediaProxyUrl(`/media/modules/${encodeURIComponent(explicitModuleName)}/${encodePath(filePath)}`, moduleName);
  }

  const relModuleMatch = normalized.match(/^([^/]+)\/(resources|ui|assets|media|static)\/(.+)$/i);
  if (relModuleMatch) {
    const [, explicitModuleName, folder, rest] = relModuleMatch;
    return mediaProxyUrl(`/media/modules/${encodeURIComponent(explicitModuleName)}/${encodePath(`${folder}/${rest}`)}`, moduleName);
  }

  return null;
}

function resolveImplicitCurrentModuleAssetSource(normalized: string, moduleName: string): string | null {
  for (const prefix of ['ui/', 'static/', 'resources/']) {
    if (normalized.startsWith(prefix)) {
      return mediaProxyUrl(`/media/modules/${encodeURIComponent(moduleName)}/${encodePath(normalized)}`, moduleName);
    }
  }
  return null;
}

export function resolveMediaUrl(raw: string, moduleName = getCurrentModule()): string {
  if (!raw || typeof raw !== 'string') return raw;

  const source = raw.trim();
  if (!source) return source;

  const passthrough = resolvePassthroughSource(source);
  if (passthrough !== null) return passthrough;

  if (isProxyMediaUrl(source)) {
    return ABSOLUTE_URL_RE.test(source)
      ? source
      : `${getCoreHttpBaseUrl()}/${source.replace(/^\/+/, '')}`;
  }

  const remote = resolveRemoteSource(source, moduleName);
  if (remote !== null) return remote;

  if (MEDIA_PREFIX_RE.test(source)) {
    return mediaProxyUrl(mediaTargetFromUrl(source), moduleName);
  }

  const normalized = source.replace(/\\/g, '/');

  if (normalized.startsWith('assets/')) {
    return `${getCoreHttpBaseUrl()}/${encodePath(normalized)}`;
  }

  const engineAsset = resolveEngineAssetSource(normalized, moduleName);
  if (engineAsset !== null) return engineAsset;

  const uploadStoragePath = resolveUploadStoragePathSource(normalized, moduleName);
  if (uploadStoragePath !== null) return uploadStoragePath;

  const extractorAsset = resolveExtractorAssetSource(normalized, moduleName);
  if (extractorAsset !== null) return extractorAsset;

  const explicitModuleAsset = resolveExplicitModuleAssetSource(normalized, moduleName);
  if (explicitModuleAsset !== null) return explicitModuleAsset;

  const implicitModuleAsset = resolveImplicitCurrentModuleAssetSource(normalized, moduleName);
  if (implicitModuleAsset !== null) return implicitModuleAsset;

  if (!normalized.startsWith('/') && !normalized.includes('://') && isStaticAsset(normalized)) {
    return `${getCoreHttpBaseUrl()}/assets/${encodePath(normalized)}`;
  }

  if (normalized.startsWith('/')) {
    return `${getCoreHttpBaseUrl()}${normalized}`;
  }

  return normalized;
}

export function authHeadersForMediaUrl(url: string, jwt?: string): Record<string, string> | undefined {
  const token = String(jwt || '').trim();
  if (!token) return undefined;
  if (!url.includes('/media/') && !url.includes('/assets/')) return undefined;
  return {
    'X-JWT': token,
    Authorization: `Bearer ${token}`,
  };
}
