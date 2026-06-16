const ABSOLUTE_URL_RE = /^https?:\/\//i;
const MEDIA_PREFIX_RE = /^\/?media\//i;
const DIRECT_MEDIA_PREFIXES = ['data:', 'blob:'] as const;
const DIRECT_MEDIA_TOKENS = ['ric.', '<svg'] as const;

function getCoreHttpBaseUrl(): string {
  const configured = String(window.__CFG__?.base_server_http_url || '').trim();
  if (configured) return configured.replace(/\/+$/, '');
  throw new Error('missing_base_server_http_url');
}

function encodePath(path: string): string {
  return path
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

function getCurrentModule(): string {
  if (typeof window === 'undefined') return 'dashboard';
  const path = window.location.pathname || '';
  const segments = path.split('/').filter(Boolean);
  return segments[0] || 'dashboard';
}

function mediaProxyUrl(target: string, moduleName = getCurrentModule()): string {
  return `${getCoreHttpBaseUrl()}/media/proxy?${new URLSearchParams({
    module_name: moduleName || 'dashboard',
    url: target,
  }).toString()}`;
}

function isProxyMediaUrl(source: string): boolean {
  if (source.startsWith('/media/proxy') || source.startsWith('media/proxy')) return true;
  try {
    const parsed = new URL(source, window.location.origin);
    return parsed.pathname === '/media/proxy';
  } catch {
    return false;
  }
}

function isStaticAsset(source: string): boolean {
  return /\.(svg|png|jpe?g|gif|webp|ico)$/i.test(source);
}

function resolvePassthroughSource(source: string): string | null {
  if (DIRECT_MEDIA_PREFIXES.some((prefix) => source.startsWith(prefix))) {
    return source;
  }
  if (DIRECT_MEDIA_TOKENS.some((prefix) => source.startsWith(prefix))) {
    return source;
  }
  return null;
}

function mediaTargetFromUrl(source: string): string {
  try {
    const parsed = new URL(source, window.location.origin);
    if (parsed.pathname.startsWith('/media/')) {
      return `${parsed.pathname}${parsed.search}`;
    }
  } catch {
    return source;
  }
  return source;
}

function resolveRemoteSource(source: string): string | null {
  if (!ABSOLUTE_URL_RE.test(source)) {
    return null;
  }
  if (isProxyMediaUrl(source)) {
    return source;
  }
  try {
    const parsed = new URL(source);
    if (parsed.pathname.startsWith('/media/')) {
      return mediaProxyUrl(mediaTargetFromUrl(source));
    }
    return mediaProxyUrl(source);
  } catch {
    return mediaProxyUrl(source);
  }
}

function resolveEngineAssetSource(normalized: string): string | null {
  const engineAssetsMatch = normalized.match(/^engines\/([^/]+)\/(.+)$/i);
  if (!engineAssetsMatch) {
    return null;
  }
  const [, engineId, filePath] = engineAssetsMatch;
  return mediaProxyUrl(`/media/engine/${encodeURIComponent(engineId)}/${encodePath(filePath)}`);
}

function resolveExtractorAssetSource(normalized: string): string | null {
  const extractorAssetsMatch = normalized.match(/^extractors\/([^/]+)\/(.+)$/i);
  if (!extractorAssetsMatch) {
    return null;
  }
  const [, extractorId, filePath] = extractorAssetsMatch;
  return mediaProxyUrl(`/media/extractors/${encodeURIComponent(extractorId)}/${encodePath(filePath)}`);
}

function resolveUploadStoragePathSource(normalized: string): string | null {
  if (!normalized.startsWith('media/')) {
    return null;
  }
  return mediaProxyUrl(`/media/uploads/by-storage-path?${new URLSearchParams({
    storage_path: normalized,
  }).toString()}`);
}

function resolveExplicitModuleAssetSource(normalized: string): string | null {
  const absLocalModuleMatch = normalized.match(/\/application\/modules\/([^/]+)\/(.+)$/i);
  if (absLocalModuleMatch) {
    const [, moduleName, filePath] = absLocalModuleMatch;
    return mediaProxyUrl(`/media/modules/${encodeURIComponent(moduleName)}/${encodePath(filePath)}`);
  }

  const absModuleMatch = normalized.match(/(?:^|\/)modules\/([^/]+)\/(.+)$/i);
  if (absModuleMatch) {
    const [, moduleName, filePath] = absModuleMatch;
    return mediaProxyUrl(`/media/modules/${encodeURIComponent(moduleName)}/${encodePath(filePath)}`);
  }

  const relModuleMatch = normalized.match(/^([^/]+)\/(resources|ui|assets|media|static)\/(.+)$/i);
  if (relModuleMatch) {
    const [, moduleName, folder, rest] = relModuleMatch;
    return mediaProxyUrl(`/media/modules/${encodeURIComponent(moduleName)}/${encodePath(`${folder}/${rest}`)}`);
  }

  return null;
}

function resolveImplicitCurrentModuleAssetSource(normalized: string): string | null {
  const currentModule = getCurrentModule();
  for (const prefix of ['ui/', 'static/', 'resources/']) {
    if (normalized.startsWith(prefix)) {
      return mediaProxyUrl(`/media/modules/${encodeURIComponent(currentModule)}/${encodePath(normalized)}`);
    }
  }
  return null;
}

export function resolveMediaUrl(raw: string): string {
  if (!raw || typeof raw !== 'string') return raw;

  const source = raw.trim();
  if (!source) return source;

  const passthrough = resolvePassthroughSource(source);
  if (passthrough !== null) {
    return passthrough;
  }

  if (isProxyMediaUrl(source)) {
    return ABSOLUTE_URL_RE.test(source)
      ? source
      : `${getCoreHttpBaseUrl()}/${source.replace(/^\/+/, '')}`;
  }

  const remote = resolveRemoteSource(source);
  if (remote !== null) {
    return remote;
  }

  if (MEDIA_PREFIX_RE.test(source)) {
    return mediaProxyUrl(mediaTargetFromUrl(source));
  }

  const normalized = source.replace(/\\/g, '/');

  if (normalized.startsWith('assets/')) {
    return `/${encodePath(normalized)}`;
  }

  const engineAsset = resolveEngineAssetSource(normalized);
  if (engineAsset !== null) {
    return engineAsset;
  }

  const uploadStoragePath = resolveUploadStoragePathSource(normalized);
  if (uploadStoragePath !== null) {
    return uploadStoragePath;
  }

  const extractorAsset = resolveExtractorAssetSource(normalized);
  if (extractorAsset !== null) {
    return extractorAsset;
  }

  const explicitModuleAsset = resolveExplicitModuleAssetSource(normalized);
  if (explicitModuleAsset !== null) {
    return explicitModuleAsset;
  }

  const implicitModuleAsset = resolveImplicitCurrentModuleAssetSource(normalized);
  if (implicitModuleAsset !== null) {
    return implicitModuleAsset;
  }

  if (!normalized.startsWith('/') && !normalized.includes('://') && isStaticAsset(normalized)) {
    return `/assets/${encodePath(normalized)}`;
  }

  return normalized;
}
