export function resolveSurfaceId(payload: any, fallback = 'main'): string {
  return String(payload?.surfaceId ?? payload?.surface_id ?? fallback);
}

function registerInlineComponentTree(components: Record<string, any>, node: any): void {
  if (!node || typeof node !== 'object') return;
  const nodeId = node.id;
  if (typeof nodeId === 'string' && nodeId.trim()) {
    components[nodeId] = node;
  }
  const childrenNode = node.children;
  const explicit = childrenNode?.explicitList;
  if (!Array.isArray(explicit)) return;
  explicit.forEach((child: any) => registerInlineComponentTree(components, child));
}

export function applySurfaceUpdate(prev: Record<string, any>, payload: any): Record<string, any> {
  const surfaceId = resolveSurfaceId(payload);
  const components = Array.isArray(payload?.components) ? payload.components : [];
  const surface = prev[surfaceId] || { components: {} };
  const nextComponents: Record<string, any> = { ...(surface.components || {}) };

  components.forEach((c: any) => {
    const id = c?.id || c?.component_id;
    if (id) {
      const key = String(id);
      nextComponents[key] = c;
      registerInlineComponentTree(nextComponents, c);
    }
  });

  return {
    ...prev,
    [surfaceId]: {
      ...surface,
      components: nextComponents,
    },
  };
}

export function applyBeginRendering(prev: Record<string, any>, payload: any): Record<string, any> {
  const surfaceId = resolveSurfaceId(payload);
  const rootId = payload?.root ?? payload?.rootId ?? payload?.root_id;
  const options = payload?.options && typeof payload.options === 'object' ? payload.options : undefined;
  return {
    ...prev,
    [surfaceId]: {
      ...(prev[surfaceId] || { components: {} }),
      rootId: rootId ? String(rootId) : undefined,
      ...(options ? { options } : {}),
    },
  };
}

export function applyDeleteSurface(prev: Record<string, any>, payload: any): Record<string, any> {
  const surfaceId = String(payload?.surfaceId ?? payload?.surface_id ?? '');
  if (!surfaceId) return prev;
  const next = { ...prev };
  delete next[surfaceId];
  return next;
}

function isPlainObject(value: any): value is Record<string, any> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function mergeDataModelValue(prev: any, next: any): any {
  if (!isPlainObject(prev) || !isPlainObject(next)) return next;

  return Object.entries(next).reduce(
    (merged, [key, value]) => ({
      ...merged,
      [key]: mergeDataModelValue(prev[key], value),
    }),
    { ...prev },
  );
}

function assignPathValue(target: Record<string, any>, path: string, value: any): void {
  const parts = String(path || '').trim().replace(/^\//, '').split('/').filter(Boolean);
  if (parts.length === 0) return;
  let cursor: Record<string, any> = target;
  parts.forEach((part, index) => {
    if (index === parts.length - 1) {
      cursor[part] = value;
      return;
    }
    const current = cursor[part];
    if (!isPlainObject(current)) cursor[part] = {};
    cursor = cursor[part];
  });
}

function normalizeDataModelPatch(data: Record<string, any>): Record<string, any> {
  return Object.entries(data).reduce((normalized, [key, value]) => {
    if (String(key).startsWith('/')) {
      assignPathValue(normalized, key, value);
      return normalized;
    }
    normalized[key] = value;
    return normalized;
  }, {} as Record<string, any>);
}

export function applyDataModelUpdate(prev: Record<string, any>, payload: any): Record<string, any> {
  const surfaceId = resolveSurfaceId(payload);
  const data = payload?.data && typeof payload.data === 'object' ? normalizeDataModelPatch(payload.data) : {};
  return {
    ...prev,
    [surfaceId]: mergeDataModelValue(prev[surfaceId] || {}, data),
  };
}
