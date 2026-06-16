const HASH_ROUTING = true;

function normalizeRoute(route: string): string {
  const raw = String(route || '').trim();
  if (!raw) return '/';

  try {
    const parsed = new URL(raw, window.location.origin);
    const path = parsed.pathname || '/';
    const search = parsed.search || '';
    return `${path}${search}`;
  } catch {
    if (raw.startsWith('?')) return `/${raw}`;
    return raw.startsWith('/') ? raw : `/${raw}`;
  }
}

function readBrowserRoute(): string {
  if (HASH_ROUTING) return normalizeRoute(location.hash.replace(/^#/, '') || '/');
  return normalizeRoute(`${location.pathname}${location.search}`);
}

function writeBrowserRoute(path: string, replace = false): void {
  const target = HASH_ROUTING
    ? '#' + (path.startsWith('/') ? path : '/' + path)
    : path;
  if (replace) history.replaceState({}, '', target);
  else history.pushState({}, '', target);
}

export { readBrowserRoute, writeBrowserRoute };
