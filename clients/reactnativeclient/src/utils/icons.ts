/**
 * Resolves a protocol-level icon spec to a RemixIcon name (stripping ri- prefix).
 */
export const resolveIconName = (icon: any): string | null => {
  const raw = String(icon?.iconName || icon || '').trim();
  if (!raw) return null;

  let resolved = raw.toLowerCase();
  if (resolved.startsWith('ric.')) resolved = resolved.slice(4);
  else if (resolved.startsWith('ri.')) resolved = resolved.slice(3);
  else if (resolved.startsWith('ri-')) resolved = resolved.slice(3);

  const map: Record<string, string> = {
    app: 'apps-2-line',
    dashboard: 'dashboard-3-line',
    settings: 'settings-2-line',
    user: 'user-3-line',
    logout: 'logout-box-line',
    chat: 'chat-3-line',
    file: 'file-line',
    folder: 'folder-line',
    plus: 'add-line',
    edit: 'edit-line',
    delete: 'delete-bin-line',
    search: 'search-line',
    filter: 'filter-3-line',
    more: 'more-2-line',
    'more-2': 'more-2-fill',
    home: 'home-line',
    person: 'user-line',
  };

  return map[resolved] || resolved;
};
