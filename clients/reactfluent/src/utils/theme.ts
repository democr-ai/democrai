export type ClientTheme = 'dark' | 'light';

export const WEB_THEME_STORAGE_KEY = 'democrai_web_theme';

export function normalizeClientTheme(value: unknown): ClientTheme {
  const raw = String(value || '').trim().toLowerCase();
  return raw === 'light' ? 'light' : 'dark';
}

export function readStoredClientTheme(): ClientTheme {
  try {
    return normalizeClientTheme(window.localStorage.getItem(WEB_THEME_STORAGE_KEY));
  } catch {
    return 'dark';
  }
}

export function applyClientTheme(theme: ClientTheme): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const normalized = normalizeClientTheme(theme);
  root.classList.toggle('dark', normalized === 'dark');
  root.setAttribute('data-client-theme', normalized);
  root.style.colorScheme = normalized;
}

export function persistClientTheme(theme: ClientTheme): void {
  try {
    window.localStorage.setItem(WEB_THEME_STORAGE_KEY, normalizeClientTheme(theme));
  } catch {
    // Ignore storage errors (private mode / quota limits).
  }
}

export function setClientTheme(theme: ClientTheme): ClientTheme {
  const normalized = normalizeClientTheme(theme);
  applyClientTheme(normalized);
  persistClientTheme(normalized);
  return normalized;
}

export function toggleClientTheme(currentTheme: ClientTheme): ClientTheme {
  return setClientTheme(currentTheme === 'dark' ? 'light' : 'dark');
}
