/**
 * Resolves a protocol-level icon spec to a CSS class (RemixIcon or internal glyph).
 */
export const resolveIconClass = (icon: any): string | null => {
  const raw = String(icon?.iconName || icon || '').trim();
  if (!raw) return null;

  if (raw.startsWith('ric.')) return `ri-${raw.slice(4)}`;
  if (raw.startsWith('ri.')) return `ri-${raw.slice(3)}`;
  if (raw.startsWith('ri-')) return raw;

  const map: Record<string, string> = {
    app: 'ri-apps-2-line',
    dashboard: 'ri-dashboard-3-line',
    settings: 'ri-settings-2-line',
    user: 'ri-user-3-line',
    logout: 'ri-logout-box-line',
    chat: 'ri-chat-3-line',
    file: 'ri-file-line',
    folder: 'ri-folder-line',
    plus: 'ri-add-line',
    edit: 'ri-edit-line',
    delete: 'ri-delete-bin-line',
    search: 'ri-search-line',
    filter: 'ri-filter-3-line',
    more: 'ri-more-2-line',
    'more-2': 'ri-more-2-fill',
  };

  return map[raw.toLowerCase()] || 'ri-apps-2-line';
};
