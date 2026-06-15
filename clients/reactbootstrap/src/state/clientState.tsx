import React from 'react';

export type ClientStateScope = 'global' | 'page' | 'auto';

export type ClientStateSnapshot = {
  global: Record<string, any>;
  page: Record<string, any>;
};

const emptyState: ClientStateSnapshot = {
  global: {},
  page: {},
};

const ClientStateContext = React.createContext<ClientStateSnapshot>(emptyState);

export const ClientStateProvider: React.FC<{
  value: ClientStateSnapshot;
  children: React.ReactNode;
}> = ({ value, children }) => (
  <ClientStateContext.Provider value={value}>{children}</ClientStateContext.Provider>
);

export function useClientStateSnapshot(): ClientStateSnapshot {
  return React.useContext(ClientStateContext);
}

export function createEmptyClientState(): ClientStateSnapshot {
  return {
    global: {},
    page: {},
  };
}

function deepCopy<T>(value: T): T {
  if (Array.isArray(value)) {
    return value.map((entry) => deepCopy(entry)) as T;
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, any>).map(([key, entry]) => [key, deepCopy(entry)]),
    ) as T;
  }
  return value;
}

function normalizeSegments(path: string): string[] {
  return String(path || '')
    .trim()
    .replace(/^\//, '')
    .split(/[/.]/)
    .filter(Boolean);
}

function getBySegments(root: any, segments: string[]): any {
  if (!segments.length) return root;
  return segments.reduce((acc, segment) => {
    if (acc == null || typeof acc !== 'object') return undefined;
    return acc[segment];
  }, root);
}

function setBySegments(root: Record<string, any>, segments: string[], value: any): void {
  if (!segments.length) return;
  let current: Record<string, any> = root;
  for (let index = 0; index < segments.length - 1; index += 1) {
    const segment = segments[index];
    const nextValue = current[segment];
    if (!nextValue || typeof nextValue !== 'object' || Array.isArray(nextValue)) {
      current[segment] = {};
    }
    current = current[segment];
  }
  current[segments[segments.length - 1]] = deepCopy(value);
}

function flattenStateValues(values: Record<string, any>): Record<string, any> {
  const flattened: Record<string, any> = {};

  const visit = (path: string, value: any): void => {
    if (Array.isArray(value) || !value || typeof value !== 'object') {
      flattened[path] = value;
      return;
    }

    const entries = Object.entries(value);
    if (!entries.length) {
      flattened[path] = value;
      return;
    }

    entries.forEach(([key, child]) => {
      const childPath = `${path}/${key}`.replace(/\/+/g, '/');
      visit(childPath, child);
    });
  };

  Object.entries(values || {}).forEach(([path, value]) => {
    visit(path.startsWith('/') ? path : `/${path}`, value);
  });

  return flattened;
}

export function readClientStateValue(
  state: ClientStateSnapshot | null | undefined,
  scope: ClientStateScope,
  path: string,
): any {
  const segments = normalizeSegments(path);
  if (!segments.length) {
    if (scope === 'page') return state?.page;
    if (scope === 'global') return state?.global;
    return state?.page ?? state?.global;
  }

  if (scope === 'page') {
    return getBySegments(state?.page, segments);
  }
  if (scope === 'global') {
    return getBySegments(state?.global, segments);
  }

  const fromPage = getBySegments(state?.page, segments);
  if (fromPage !== undefined) return fromPage;
  return getBySegments(state?.global, segments);
}

export function useClientStateValue(path: string, scope: ClientStateScope = 'auto'): any {
  const state = useClientStateSnapshot();
  return React.useMemo(() => readClientStateValue(state, scope, path), [state, scope, path]);
}

export function updateClientState(
  prev: ClientStateSnapshot,
  values: Record<string, any>,
  scope: Exclude<ClientStateScope, 'auto'>,
): ClientStateSnapshot {
  const next: ClientStateSnapshot = {
    global: deepCopy(prev.global),
    page: deepCopy(prev.page),
  };
  const target = scope === 'global' ? next.global : next.page;
  Object.entries(flattenStateValues(values || {})).forEach(([path, value]) => {
    const segments = normalizeSegments(path);
    if (!segments.length) return;
    setBySegments(target, segments, value);
  });
  return next;
}

function collectionItems(value: any): any[] {
  return Array.isArray(value) ? value.map((entry) => deepCopy(entry)) : [deepCopy(value)];
}

function resolveCollectionIndex(items: any[], payload: any): number | null {
  if (typeof payload === 'number') {
    return payload >= 0 && payload < items.length ? payload : null;
  }
  if (payload && typeof payload === 'object') {
    if (typeof payload.index === 'number') {
      return payload.index >= 0 && payload.index < items.length ? payload.index : null;
    }
    const targetId = payload.id;
    if (targetId == null) return null;
    const index = items.findIndex((entry) => {
      if (typeof entry === 'string') return entry === String(targetId);
      if (!entry || typeof entry !== 'object') return false;
      return String(entry.id ?? '') === String(targetId);
    });
    return index >= 0 ? index : null;
  }
  if (typeof payload === 'string') {
    const index = items.findIndex((entry) => {
      if (typeof entry === 'string') return entry === payload;
      if (!entry || typeof entry !== 'object') return false;
      return String(entry.id ?? '') === payload;
    });
    return index >= 0 ? index : null;
  }
  return null;
}

function patchCollection(items: any, action: string, value: any): any[] | null {
  const current = Array.isArray(items) ? items.map((entry) => deepCopy(entry)) : [];
  if (action === 'set') {
    return Array.isArray(value) ? value.map((entry) => deepCopy(entry)) : [];
  }
  if (action === 'append') {
    return [...current, ...collectionItems(value)];
  }
  if (action === 'prepend') {
    return [...collectionItems(value), ...current];
  }
  if (action === 'remove') {
    const index = resolveCollectionIndex(current, value);
    if (index == null) return current;
    current.splice(index, 1);
    return current;
  }
  if (action === 'replace') {
    const index = resolveCollectionIndex(current, value);
    const replacement = value && typeof value === 'object' ? value.item : undefined;
    if (index == null || replacement === undefined) return current;
    current[index] = deepCopy(replacement);
    return current;
  }
  return null;
}

export function patchClientState(prev: ClientStateSnapshot, patch: Record<string, any>): ClientStateSnapshot {
  const scope = String(patch?.scope || 'page').toLowerCase() === 'global' ? 'global' : 'page';
  const path = String(patch?.path || patch?.key || '').trim();
  const action = String(patch?.action || patch?.op || '').trim();
  const segments = normalizeSegments(path);
  if (!segments.length || !action) return prev;

  const next: ClientStateSnapshot = {
    global: deepCopy(prev.global),
    page: deepCopy(prev.page),
  };
  const target = scope === 'global' ? next.global : next.page;
  const current = getBySegments(target, segments);
  const patched = patchCollection(current, action, patch.value);
  if (patched == null) return prev;
  setBySegments(target, segments, patched);
  return next;
}

export function setCurrentPath(prev: ClientStateSnapshot, nextPath: string): ClientStateSnapshot {
  const currentPath = String(readClientStateValue(prev, 'global', '/current_path') || '');
  if (currentPath === nextPath) return prev;

  const nextGlobal = deepCopy(prev.global);
  setBySegments(nextGlobal, ['current_path'], nextPath);
  const currentPage = (() => {
    try {
      return new URL(currentPath || '/', window.location.origin).pathname || '/';
    } catch {
      return String(currentPath || '/').split('?')[0].split('#')[0] || '/';
    }
  })();
  const nextPage = (() => {
    try {
      return new URL(nextPath || '/', window.location.origin).pathname || '/';
    } catch {
      return String(nextPath || '/').split('?')[0].split('#')[0] || '/';
    }
  })();
  return {
    global: nextGlobal,
    page: currentPage === nextPage ? deepCopy(prev.page) : {},
  };
}
