export type NormalizedPropertyUpdate = {
  componentId: string;
  propertyName: string;
  value: any;
  action: string;
  surfaceId: string;
};

export function normalizePropertyUpdate(update: any): NormalizedPropertyUpdate | null {
  if (!update || typeof update !== 'object') return null;

  const componentIdRaw = update.componentId ?? update.component_id;
  const propertyNameRaw = update.propertyName ?? update.property_name;
  if (!componentIdRaw || !propertyNameRaw) return null;

  return {
    componentId: String(componentIdRaw),
    propertyName: String(propertyNameRaw),
    value: update.value,
    action: String(update.action ?? update.op ?? 'set'),
    surfaceId: update.surfaceId ?? update.surface_id ? String(update.surfaceId ?? update.surface_id) : '',
  };
}

type ApplyUpdateFn = (update: NormalizedPropertyUpdate) => void;

function collectionItems(value: any): any[] {
  if (Array.isArray(value)) return value;
  return [value];
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
    if (targetId != null) {
      const idx = items.findIndex((entry: any) => {
        if (typeof entry === 'string') return entry === String(targetId);
        if (!entry || typeof entry !== 'object') return false;
        return String(entry.id ?? '') === String(targetId);
      });
      return idx >= 0 ? idx : null;
    }
    return null;
  }

  if (typeof payload === 'string') {
    const idx = items.findIndex((entry: any) => {
      if (typeof entry === 'string') return entry === payload;
      if (!entry || typeof entry !== 'object') return false;
      return String(entry.id ?? '') === payload;
    });
    return idx >= 0 ? idx : null;
  }

  return null;
}

function patchCollection(items: any[], action: string, value: any): any[] | null {
  const current = Array.isArray(items) ? [...items] : [];

  if (action === 'set') {
    return Array.isArray(value) ? [...value] : [];
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
    current[index] = replacement;
    return current;
  }

  return null;
}

const COLLECTION_PROPERTY_NAMES = new Set([
  'actions',
  'attachments',
  'components',
  'items',
  'messages',
  'options',
  'tabs',
  'threads',
]);

function isCollectionProperty(path: string): boolean {
  const leaf = path.split('.').filter(Boolean).pop() || path;
  return COLLECTION_PROPERTY_NAMES.has(leaf);
}

function setDeepValue(target: Record<string, any>, path: string, value: any, action: string): Record<string, any> {
  const next = { ...target };
  const segments = path.split('.').filter(Boolean);
  if (segments.length === 0) return next;

  let cursor: any = next;
  for (let i = 0; i < segments.length - 1; i += 1) {
    const key = segments[i];
    cursor[key] = cursor[key] && typeof cursor[key] === 'object' ? { ...cursor[key] } : {};
    cursor = cursor[key];
  }

  const leaf = segments[segments.length - 1];
  const currentLeaf = cursor[leaf];
  const patchedCollection = patchCollection(currentLeaf, action, value);

  if (patchedCollection && (Array.isArray(currentLeaf) || isCollectionProperty(path))) {
    cursor[leaf] = patchedCollection;
  } else if (action === 'append' && typeof currentLeaf === 'string') {
    cursor[leaf] = (cursor[leaf] || '') + String(value ?? '');
  } else if (action === 'append' && cursor[leaf] == null && (leaf === 'text' || leaf === 'value')) {
    cursor[leaf] = String(value ?? '');
  } else {
    cursor[leaf] = value;
  }

  return next;
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

function patchChildrenNode(existingChildren: any, propertyName: string, value: any, action: string): any {
  const isChildrenPatch = propertyName === 'children' || propertyName.startsWith('children.');
  if (!isChildrenPatch) return existingChildren;

  const baseChildren = existingChildren && typeof existingChildren === 'object'
    ? { ...existingChildren }
    : {};

  if (propertyName === 'children') {
    const currentExplicit = Array.isArray(baseChildren.explicitList) ? baseChildren.explicitList : [];
    const patched = patchCollection(currentExplicit, action, value);
    if (patched) {
      baseChildren.explicitList = patched;
      return baseChildren;
    }
    baseChildren.explicitList = Array.isArray(value) ? value : [];
    return baseChildren;
  }

  const nestedPath = propertyName.slice('children.'.length);
  if (nestedPath === 'explicitList') {
    const currentExplicit = Array.isArray(baseChildren.explicitList) ? baseChildren.explicitList : [];
    const patched = patchCollection(currentExplicit, action, value);
    if (patched) {
      baseChildren.explicitList = patched;
      return baseChildren;
    }
    baseChildren.explicitList = action === 'set' && Array.isArray(value) ? value : currentExplicit;
    return baseChildren;
  }

  return setDeepValue(baseChildren, nestedPath, value, action);
}

function applyUpdateToComponentNode(component: any, normalized: NormalizedPropertyUpdate): any {
  const { propertyName, value, action } = normalized;
  const type = Object.keys(component?.component || {})[0];
  if (!type) return component;
  const oldProps = component.component[type] || {};
  const isChildrenPatch = propertyName === 'children' || propertyName.startsWith('children.');
  const nextProps = isChildrenPatch ? oldProps : setDeepValue(oldProps, propertyName, value, action);
  const nextChildren = patchChildrenNode(component.children, propertyName, value, action);
  return {
    ...component,
    component: { [type]: nextProps },
    children: nextChildren,
  };
}

function updateInlineTreeNode(node: any, normalized: NormalizedPropertyUpdate): { node: any; found: boolean } {
  if (!node || typeof node !== 'object') return { node, found: false };
  const componentId = normalized.componentId;
  if (String(node.id ?? '') === componentId) {
    const updated = applyUpdateToComponentNode(node, normalized);
    return { node: updated, found: true };
  }

  const explicit = node?.children?.explicitList;
  if (!Array.isArray(explicit) || explicit.length === 0) {
    return { node, found: false };
  }

  let found = false;
  const nextExplicit = explicit.map((child: any) => {
    if (!child || typeof child !== 'object') return child;
    const updated = updateInlineTreeNode(child, normalized);
    if (updated.found) found = true;
    return updated.node;
  });

  if (!found) return { node, found: false };
  return {
    node: {
      ...node,
      children: {
        ...(node.children || {}),
        explicitList: nextExplicit,
      },
    },
    found: true,
  };
}

export function applyPropertyUpdateToSurfaces(
  prev: Record<string, any>,
  normalized: NormalizedPropertyUpdate,
): Record<string, any> {
  const { componentId, propertyName, value, action, surfaceId: requestedSurfaceId } = normalized;

  let resolvedSurfaceId = requestedSurfaceId;
  let surface = resolvedSurfaceId ? prev[resolvedSurfaceId] : undefined;
  if (!surface) {
    const foundSurfaceId = Object.keys(prev).find((sid) => Boolean(prev[sid]?.components?.[componentId]));
    if (foundSurfaceId) {
      resolvedSurfaceId = foundSurfaceId;
      surface = prev[resolvedSurfaceId];
    }
  }

  if (surface) {
    const component = surface.components?.[componentId];
    if (component) {
      const isChildrenPatch = propertyName === 'children' || propertyName.startsWith('children.');
      const nextComponent = applyUpdateToComponentNode(component, normalized);
      const nextComponents = { ...surface.components };
      nextComponents[componentId] = nextComponent;

      if (isChildrenPatch) {
        const explicit = nextComponent?.children?.explicitList;
        if (Array.isArray(explicit)) {
          explicit.forEach((child: any) => registerInlineComponentTree(nextComponents, child));
        }
      }

      Object.entries(nextComponents).forEach(([nodeId, node]) => {
        if (nodeId === componentId) return;
        const updated = updateInlineTreeNode(node, normalized);
        if (updated.found) {
          nextComponents[nodeId] = updated.node;
          registerInlineComponentTree(nextComponents, updated.node);
        }
      });

      return {
        ...prev,
        [resolvedSurfaceId]: {
          ...surface,
          components: nextComponents,
        },
      };
    }
  }

  const surfaceOrder = requestedSurfaceId
    ? [requestedSurfaceId, ...Object.keys(prev).filter((sid) => sid !== requestedSurfaceId)]
    : Object.keys(prev);

  for (const sid of surfaceOrder) {
    const currentSurface = prev[sid];
    if (!currentSurface || typeof currentSurface !== 'object') continue;
    const componentsMap = currentSurface.components || {};
    if (!componentsMap || typeof componentsMap !== 'object') continue;

    let foundInline = false;
    const nextComponents: Record<string, any> = { ...componentsMap };

    Object.entries(componentsMap).forEach(([rootId, rootNode]) => {
      const updated = updateInlineTreeNode(rootNode, normalized);
      if (updated.found) {
        foundInline = true;
        nextComponents[rootId] = updated.node;
        registerInlineComponentTree(nextComponents, updated.node);
      }
    });

    if (foundInline) {
      return {
        ...prev,
        [sid]: {
          ...currentSurface,
          components: nextComponents,
        },
      };
    }
  }

  return prev;
}
export class PropertyUpdateController {
  private readonly pending = new Map<string, NormalizedPropertyUpdate>();

  private sequence = 0;

  private flushTimer: any = null;

  private readonly applyUpdate: ApplyUpdateFn;

  constructor(applyUpdate: ApplyUpdateFn) {
    this.applyUpdate = applyUpdate;
  }

  enqueue(rawUpdate: any): void {
    const normalized = normalizePropertyUpdate(rawUpdate);
    if (!normalized) return;

    const { componentId, propertyName, action, value, surfaceId } = normalized;
    const key = `${surfaceId || '*'}::${componentId}::${propertyName}`;
    const pending = this.pending.get(key);

    if (action === 'append' && (propertyName === 'text' || propertyName === 'value')) {
      const appendValue = String(value ?? '');
      if (pending && pending.action === 'append') {
        this.pending.set(key, {
          ...pending,
          value: `${pending.value ?? ''}${appendValue}`,
        });
      } else {
        this.pending.set(key, {
          ...normalized,
          action: 'append',
          value: appendValue,
        });
      }
    } else if (action === 'append' || action === 'prepend' || action === 'remove' || action === 'replace') {
      const patchKey = `${key}::${this.sequence++}`;
      this.pending.set(patchKey, normalized);
    } else {
      this.pending.set(key, normalized);
    }

    if (this.flushTimer == null) {
      this.flushTimer = setTimeout(() => this.flush(), 0);
    }
  }

  flush(): void {
    if (this.flushTimer != null) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }

    const updates = Array.from(this.pending.values());
    this.pending.clear();
    updates.forEach((update) => this.applyUpdate(update));
  }

  dispose(): void {
    if (this.flushTimer != null) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    this.pending.clear();
  }
}
