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
  explicit.forEach((child) => registerInlineComponentTree(components, child));
}

export function applySurfaceUpdate(prev: Record<string, any>, payload: any): Record<string, any> {
  const surfaceId = resolveSurfaceId(payload);
  const components = Array.isArray(payload?.components) ? payload.components : [];
  const surface = prev[surfaceId] || { components: {} };
  const nextComponents: Record<string, any> = { ...(surface.components || {}) };

  components.forEach((c: any) => {
    if (c?.id) {
      const key = String(c.id);
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
  const options = payload?.options && typeof payload.options === 'object' ? payload.options : undefined;
  return {
    ...prev,
    [surfaceId]: {
      ...(prev[surfaceId] || { components: {} }),
      rootId: payload?.root,
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

export function applyDataModelUpdate(prev: Record<string, any>, payload: any): Record<string, any> {
  const surfaceId = resolveSurfaceId(payload);
  const data = payload?.data && typeof payload.data === 'object' ? payload.data : {};
  return {
    ...prev,
    [surfaceId]: mergeDataModelValue(prev[surfaceId] || {}, data),
  };
}
