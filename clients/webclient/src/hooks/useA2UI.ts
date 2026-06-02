import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { normalizeWsCodec, type WsCodec } from '../utils/wsCodec';
import { createA2UITransport, type A2UITransport, type A2UITransportKind } from '../runtime/transport/a2uiTransport';
import { recordExternalAccessDecisionAck } from '../runtime/controllers/external_access';
import { applyPropertyUpdateToSurfaces, normalizePropertyUpdate } from '../runtime/controllers/property_updates';
import { dispatchBackgroundTaskEvent } from '../runtime/background_task_events';
import { createRuntimeComposition } from '../runtime/composition';
import {
  applyBeginRendering,
  applyDataModelUpdate,
  applyDeleteSurface,
  applySurfaceUpdate,
} from '../runtime/controllers/surfaces';
import {
  createEmptyClientState,
  patchClientState,
  readClientStateValue,
  setCurrentPath,
  updateClientState,
  type ClientStateSnapshot,
} from '../state/clientState';
import { getJwt, setJwt as setAuthJwt } from '../state/authStore';
import {
  inferModuleNameFromAction,
  materializeAttachmentUploads,
  sanitizeAttachmentEntriesForTransport,
} from '../utils/uploads';

import {readBrowserRoute, writeBrowserRoute} from '../utils/router'

type Component = {
  id: string;
  component: Record<string, any>;
  children?: any;
  permissions?: string[];
};

type Surface = {
  components: Record<string, Component>;
  rootId?: string;
};

export type BackgroundTaskInfo = {
  taskId: string;
  label: string;
  plugin: string;
  status: 'started' | 'running' | 'completed' | 'failed' | 'waiting_confirmation';
  progress: number;
  result?: any;
  error?: string;
  confirmSurfaceId?: string;
  confirmComponents?: any[];
};

export type UseA2UIOptions = {
  url?: string;
  codec?: WsCodec | string;
  transport?: A2UITransportKind | string;
};

type ClientActionMeta = {
  collectInputIds?: string[];
  uploadInputIds?: string[];
};

type PendingRequestTimer = ReturnType<typeof window.setTimeout>;

const PENDING_ACTION_TIMEOUT_MS = 15000;
const NOTIFICATION_POLL_INTERVAL_MS = 30000;
const TOKEN_REFRESH_LEAD_SECONDS = 60;
const TOKEN_REFRESH_RETRY_SECONDS = 30;
const TOKEN_REFRESH_FALLBACK_SECONDS = 300;
const TOKEN_REFRESH_MIN_DELAY_MS = 1000;

function isDebugEnabled(): boolean {
  const envFlag = String(import.meta.env.VITE_A2UI_DEBUG || '').trim().toLowerCase();
  if (['1', 'true', 'yes', 'on'].includes(envFlag)) return true;
  const storageFlag = String(localStorage.getItem('democrai_web_debug') || '').trim().toLowerCase();
  return ['1', 'true', 'yes', 'on'].includes(storageFlag);
}

function debugLog(scope: string, ...args: any[]): void {
  if (!isDebugEnabled()) return;
  // eslint-disable-next-line no-console
  console.debug(`[webclient:${scope}]`, ...args);
}

function summarizeDebugValue(value: any): Record<string, any> {
  if (Array.isArray(value)) return { type: 'array', length: value.length };
  if (value && typeof value === 'object') return { type: 'object', keys: Object.keys(value) };
  if (typeof value === 'string') return { type: 'string', length: value.length };
  return { type: typeof value };
}

function summarizeDebugMessage(msg: any): Record<string, any> {
  if (!msg || typeof msg !== 'object') return { type: typeof msg };
  const value = msg.value && typeof msg.value === 'object' ? msg.value : null;
  const nestedMessage = msg.message && typeof msg.message === 'object' ? msg.message : null;
  return {
    keys: Object.keys(msg),
    type: msg.type,
    kind: msg.kind,
    action: msg.action,
    requestId: msg.request_id || msg.requestId,
    streamId: msg.stream_id || msg.streamId,
    surfaceId: msg.surface_id || msg.surfaceId,
    componentId: msg.component_id || msg.componentId,
    propertyName: msg.property_name || msg.propertyName,
    messages: Array.isArray(msg.messages) ? msg.messages.length : undefined,
    hasMessage: Boolean(msg.message),
    messageKeys: nestedMessage ? Object.keys(nestedMessage) : undefined,
    messageType: nestedMessage?.type,
    valueType: value?.type,
    valueKind: value?.kind,
    valueRequestId: value?.request_id || value?.requestId,
    payloadKeys: msg.payload && typeof msg.payload === 'object' ? Object.keys(msg.payload) : undefined,
    value: summarizeDebugValue(msg.value),
  };
}

function getDefaultWsUrl(): string {
  return window.__CFG__.base_server_ws_url
}

function getCoreHttpBaseUrl(): string {
  return window.__CFG__.base_server_http_url
}

function resolveWindowActionUrl(raw: string): string {
  const value = String(raw || '').trim();
  if (!value) return '';
  if (value.startsWith('/')) {
    return `${getCoreHttpBaseUrl()}${value}`;
  }
  return value;
}

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

function resolveClientPath(root: any, path: any): any {
  const raw = String(path || '').trim();
  if (!raw || raw === '/') return root;
  const segments = raw
    .replace(/^\//, '')
    .split(/[/.]/)
    .filter(Boolean);
  return segments.reduce((acc: any, segment: string) => {
    if (acc == null || typeof acc !== 'object') return undefined;
    return acc[segment];
  }, root);
}

function componentPropsFromSurface(surfaces: Record<string, Surface>, surfaceId: string, componentId: string): any {
  const surface = surfaces?.[surfaceId];
  const component = surface?.components?.[componentId]
    || Object.values(surfaces || {}).find((entry: any) => entry?.components?.[componentId])?.components?.[componentId];
  const componentBody = component?.component || {};
  const componentType = Object.keys(componentBody)[0];
  if (!componentType) return undefined;
  return componentBody[componentType];
}

function routeFromCurrentPathMessage(value: any): string {
  if (typeof value === 'object' && value) {
    const appName = value.app_name || 'dashboard';
    const pagePath = value.page_path || 'index';
    const path = normalizeRoute(`/${appName}/${pagePath}`);

    const params = value.params && typeof value.params === 'object' ? value.params : {};
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, rawVal]) => {
      if (rawVal == null) return;
      if (Array.isArray(rawVal)) {
        rawVal.forEach((item) => {
          if (item != null) searchParams.append(key, String(item));
        });
        return;
      }
      searchParams.set(key, String(rawVal));
    });

    const qs = searchParams.toString();
    return qs ? `${path}?${qs}` : path;
  }

  return normalizeRoute(String(value || '/'));
}

async function downloadWindowActionUrl(url: string, filename: string): Promise<void> {
  const resolvedUrl = resolveWindowActionUrl(url);
  if (!resolvedUrl) return;

  const headers: Record<string, string> = { Accept: '*/*' };
  const jwt = getJwt();
  if (jwt) headers['X-JWT'] = jwt;

  const response = await fetch(resolvedUrl, {
    method: 'GET',
    headers,
    credentials: 'include',
  });
  if (!response.ok) {
    throw new Error(`Download failed with status ${response.status}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = String(filename || '').trim() || 'download';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

function decodeJwtClaims(token: string): { role: string; permissions: string[] } {
  try {
    const parts = token.split('.');
    if (parts.length < 2) return { role: 'Guest', permissions: [] };

    const payloadBase64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = payloadBase64 + '='.repeat((4 - (payloadBase64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));

    const role = String(payload?.role || 'Guest');
    const permissions = Array.isArray(payload?.permissions)
      ? payload.permissions.map((p: any) => String(p))
      : [];

    return { role, permissions };
  } catch {
    return { role: 'Guest', permissions: [] };
  }
}

function decodeJwtExpiry(token: string): number | null {
  try {
    const parts = token.split('.');
    if (parts.length < 2) return null;

    const payloadBase64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = payloadBase64 + '='.repeat((4 - (payloadBase64.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    const exp = Number(payload?.exp);
    return Number.isFinite(exp) ? Math.trunc(exp) : null;
  } catch {
    return null;
  }
}

function messagePriority(data: any): number {
  if (Array.isArray(data?.messages) && data.messages.length > 0) {
    return Math.min(...data.messages.map((entry: any) => messagePriority(entry)));
  }

  if (data.beginRendering || data.surfaceUpdate || data.deleteSurface || data.dataModelUpdate) return 0;
  if (data.begin_rendering || data.surface_update || data.delete_surface || data.data_model_update) return 0;
  if (data.current_path !== undefined) return 0;
  if (data.type === 'hot_reload') return 0;

  if (data.windowAction || data.statePatch || data.state_patch || data.stateUpdate) return 1;
  if (
    data.backgroundTaskStarted ||
    data.backgroundTaskProgress ||
    data.backgroundTaskCompleted ||
    data.backgroundTaskError ||
    data.backgroundTaskConfirmation ||
    data.background_task_started ||
    data.background_task_progress ||
    data.background_task_completed ||
    data.background_task_error ||
    data.background_task_confirmation
  ) {
    return 1;
  }

  const update = data.propertyUpdate || data.property_update;
  if (update && typeof update === 'object') {
    const prop = String(update.propertyName ?? update.property_name ?? '');
    const action = String(update.action ?? update.op ?? 'set');

    if (action === 'append' && (prop === 'text' || prop === 'value')) return 3;
    if (prop === 'scroll') return 4;
    return 2;
  }

  return 2;
}

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

  if (patchedCollection && Array.isArray(currentLeaf)) {
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

function patchChildrenNode(existingChildren: any, propertyName: string, value: any, action: string): any {
  const isChildrenPatch = propertyName === 'children' || propertyName.startsWith('children.');
  if (!isChildrenPatch) return existingChildren;

  const baseChildren = existingChildren && typeof existingChildren === 'object'
    ? { ...existingChildren }
    : {};

  // Most collection patches target "children".
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

  // Nested updates like children.explicitList.
  if (propertyName.startsWith('children.')) {
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

  return baseChildren;
}

function resolveHookOptions(options?: string | UseA2UIOptions): UseA2UIOptions {
  if (!options) return {};
  if (typeof options === 'string') return { url: options };
  return options;
}

function normalizeTransportKind(value: unknown): A2UITransportKind {
  const normalized = String(value || '').trim().toLowerCase();
  if (normalized === 'tauri-ipc') return 'tauri-ipc';
  if (normalized === 'websocket') return 'websocket';
  return 'auto';
}

function shouldAttachInputsForAction(actionName: string, context: any): boolean {
  const hasExplicitContext =
    context &&
    typeof context === 'object' &&
    !Array.isArray(context) &&
    Object.keys(context).length > 0;
  if (hasExplicitContext) return false;

  const name = String(actionName || '').trim().toLowerCase();
  if (!name) return false;
  return (
    name.includes('login') ||
    name.includes('signin') ||
    name.includes('auth') ||
    name.includes('session')
  );
}

function extractClientActionMeta(context: any): { cleanContext: Record<string, any>; meta: ClientActionMeta } {
  if (!context || typeof context !== 'object' || Array.isArray(context)) {
    return { cleanContext: {}, meta: {} };
  }

  const cleanContext: Record<string, any> = { ...context };
  const uploadInputIds = normalizeClientInputIds(
    cleanContext.upload_input_ids ?? cleanContext.upload_input_id,
  );
  delete cleanContext.upload_input_ids;
  delete cleanContext.upload_input_id;
  const rawMeta = cleanContext.__client__;
  delete cleanContext.__client__;

  if (!rawMeta || typeof rawMeta !== 'object' || Array.isArray(rawMeta)) {
    return { cleanContext, meta: { uploadInputIds } };
  }

  const rawIds = Array.isArray((rawMeta as any).collect_input_ids) ? (rawMeta as any).collect_input_ids : [];
  const collectInputIds = rawIds
    .map((entry: any) => String(entry || '').trim())
    .filter(Boolean);

  return {
    cleanContext,
    meta: {
      collectInputIds: collectInputIds.length > 0 ? collectInputIds : undefined,
      uploadInputIds,
    },
  };
}

function normalizeClientInputIds(raw: any): string[] | undefined {
  if (Array.isArray(raw)) {
    const values = raw
      .map((entry: any) => String(entry || '').trim())
      .filter(Boolean);
    return values.length > 0 ? values : undefined;
  }
  const single = String(raw || '').trim();
  return single ? [single] : undefined;
}

function sanitizeOutboundValue(value: any): any {
  if (Array.isArray(value)) return sanitizeAttachmentEntriesForTransport(value);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [key, sanitizeOutboundValue(nested)]),
    );
  }
  return value;
}

function collectInboundRequestIds(message: any, result: Set<string> = new Set()): Set<string> {
  if (!message || typeof message !== 'object') return result;

  const directRequestId = String((message as any).request_id || '').trim();
  if (directRequestId) result.add(directRequestId);

  const nestedRequestId = String((message as any)?.actionBusy?.requestId || '').trim();
  if (nestedRequestId) result.add(nestedRequestId);

  const bindingRequestId = String((message as any)?.bindingActionResult?.requestId || '').trim();
  if (bindingRequestId) result.add(bindingRequestId);

  if (Array.isArray((message as any).messages)) {
    (message as any).messages.forEach((entry: any) => collectInboundRequestIds(entry, result));
  }

  if ((message as any).message && typeof (message as any).message === 'object') {
    collectInboundRequestIds((message as any).message, result);
  }

  return result;
}

export function useA2UI(options?: string | UseA2UIOptions) {
  const resolvedOptions = useMemo(() => resolveHookOptions(options), [options]);
  const wsCodec = useMemo(
    () => normalizeWsCodec(resolvedOptions.codec || localStorage.getItem('democrai_ws_codec') || 'json'),
    [resolvedOptions.codec],
  );
  const transportKind = useMemo(
    () => normalizeTransportKind(resolvedOptions.transport || import.meta.env.VITE_A2UI_TRANSPORT),
    [resolvedOptions.transport],
  );
  const wsUrl = useMemo(() => {
    const base = resolvedOptions.url || getDefaultWsUrl();
    const glue = base.includes('?') ? '&' : '?';
    return `${base}${glue}codec=${encodeURIComponent(wsCodec)}`;
  }, [resolvedOptions.url, wsCodec]);

  const [surfaces, setSurfaces] = useState<Record<string, Surface>>({ main: { components: {} } });
  const [dataModel, setDataModel] = useState<Record<string, Record<string, any>>>({ main: {} });
  const [stateModel, setStateModel] = useState<ClientStateSnapshot>(createEmptyClientState);
  const [inputs, setInputs] = useState<Record<string, any>>({});
  const [backgroundTasks, setBackgroundTasks] = useState<Record<string, BackgroundTaskInfo>>({});
  const [notificationCount, setNotificationCount] = useState<number>(0);
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [userRole, setUserRole] = useState('Guest');
  const [userPermissions, setUserPermissions] = useState<string[]>([]);
  const [pendingActions, setPendingActions] = useState<Record<string, number>>({});

  const transportRef = useRef<A2UITransport | null>(null);
  const runtimeRef = useRef<ReturnType<typeof createRuntimeComposition> | null>(null);
  const surfacesRef = useRef<Record<string, Surface>>({ main: { components: {} } });
  const dataModelRef = useRef<Record<string, Record<string, any>>>({ main: {} });
  const stateModelRef = useRef<ClientStateSnapshot>(createEmptyClientState());
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectDelayRef = useRef<number>(1000);
  const heartbeatTimerRef = useRef<number | null>(null);
  const notificationPollTimerRef = useRef<number | null>(null);
  const tokenRefreshTimerRef = useRef<number | null>(null);
  const tokenExpiryRef = useRef<number | null>(null);
  const lastAuthContextRequestRef = useRef<{ key: string; at: number }>({ key: '', at: 0 });
  const isAuthenticatedRef = useRef<boolean>(false);
  const inputsRef = useRef<Record<string, any>>({});
  const jwtRef = useRef('');
  const pendingActionsRef = useRef<Record<string, number>>({});
  const pendingRequestsRef = useRef<Record<string, string>>({});
  const pendingTimeoutsRef = useRef<Record<string, PendingRequestTimer>>({});

  //const browserPathRef = useRef<string>(normalizeRoute(`${window.location.pathname || '/'}${window.location.search || ''}`));
  const browserPathRef = useRef<string>(readBrowserRoute());
  const hasSyncedBrowserPathRef = useRef<boolean>(false);
  const authSessionSyncQueueRef = useRef<Promise<void>>(Promise.resolve());
  const authSessionSyncPendingRef = useRef<number>(0);
  const authSessionSyncVersionRef = useRef<number>(0);
  const authSessionCookieReconnectDoneRef = useRef<boolean>(false);

  useEffect(() => {
    surfacesRef.current = surfaces;
  }, [surfaces]);

  useEffect(() => {
    dataModelRef.current = dataModel;
  }, [dataModel]);

  useEffect(() => {
    stateModelRef.current = stateModel;
  }, [stateModel]);

  const clearTokenRefreshTimer = useCallback(() => {
    if (tokenRefreshTimerRef.current != null) {
      window.clearTimeout(tokenRefreshTimerRef.current);
      tokenRefreshTimerRef.current = null;
    }
  }, []);

  const persistJwt = useCallback((token: string) => {
    jwtRef.current = token;
    setAuthJwt(token);

    if (token) {
      tokenExpiryRef.current = decodeJwtExpiry(token);
      const claims = decodeJwtClaims(token);
      setUserRole(claims.role);
      setUserPermissions(claims.permissions);
      return;
    }
    tokenExpiryRef.current = null;
  }, []);

  const applyAuthState = useCallback((payload: any) => {
    const role = typeof payload?.role === 'string' ? payload.role : 'Guest';
    const permissions = Array.isArray(payload?.permissions)
      ? payload.permissions.map((entry: any) => String(entry))
      : [];
    const hasPermissionsPayload = Array.isArray(payload?.permissions);
    const permissionsLoaded = Boolean(payload?.permissions_loaded) || (Boolean(payload?.authenticated) && hasPermissionsPayload);
    const user = payload?.user_id ?? payload?.user;
    const hasUser = user !== null && user !== undefined && String(user).trim() !== '';
    const authenticated = Boolean(payload?.authenticated) || hasUser || role.toLowerCase() !== 'guest';
    isAuthenticatedRef.current = authenticated;
    if (!authenticated) {
      tokenExpiryRef.current = null;
      lastAuthContextRequestRef.current = { key: '', at: 0 };
    }
    setUserRole(role);
    setUserPermissions(permissions);
    const userValue = payload?.user && typeof payload.user === 'object'
      ? payload.user
      : hasUser
        ? { id: user }
        : null;
    setStateModel((prev) => updateClientState(prev, {
      '/auth/authenticated': authenticated,
      '/auth/user': authenticated ? userValue : null,
      '/auth/role': authenticated ? role : 'Guest',
      '/auth/permissions': authenticated ? permissions : [],
      '/auth/permissions_loaded': authenticated ? permissionsLoaded : false,
    }, 'global'));
  }, []);

  const reconnect = useCallback(() => {
    if (reconnectTimerRef.current != null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    const transport = transportRef.current;
    if (transport && (transport.isOpen() || transport.isConnecting())) {
      transport.close();
    }
  }, []);

  const clearClientAuthSession = useCallback((payload?: any) => {
    applyAuthState(payload || null);
    persistJwt('');
    authSessionCookieReconnectDoneRef.current = false;
    clearTokenRefreshTimer();
    reconnect();
  }, [applyAuthState, clearTokenRefreshTimer, persistJwt, reconnect]);

  const sendRaw = useCallback((payload: any) => {
    const transport = transportRef.current;
    if (!transport || !transport.isOpen()) {
      debugLog('transport:send:skip', { payload });
      return false;
    }
    const jwt = jwtRef.current || undefined;
    const outbound = jwt && payload && typeof payload === 'object' && !Array.isArray(payload) && payload.jwt === undefined
      ? { ...payload, jwt }
      : payload;
    debugLog('transport:send', outbound);
    return transport.send(outbound);
  }, []);

  const respondToClientQuery = useCallback((query: any) => {
    const requestId = String(query?.requestId || query?.request_id || '').trim();
    if (!requestId) return;

    const sendResult = (result: any) => {
      sendRaw({ clientQueryResult: { requestId, ...result } });
    };

    try {
      const kind = String(query?.kind || '').trim();
      const surfaceId = String(query?.surfaceId || query?.surface_id || 'main');
      const path = query?.path;
      let value: any;

      if (kind === 'store_value' || kind === 'current_store_value') {
        const scope = String(query?.scope || 'auto').toLowerCase() as 'auto' | 'page' | 'global';
        value = readClientStateValue(stateModelRef.current, scope, String(path || '/'));
      } else if (kind === 'data_value' || kind === 'current_data_value') {
        value = resolveClientPath(dataModelRef.current?.[surfaceId] || {}, path);
      } else if (kind === 'component_props' || kind === 'current_component_props') {
        const componentId = String(query?.componentId || query?.component_id || '').trim();
        value = componentPropsFromSurface(surfacesRef.current, surfaceId, componentId);
      } else if (kind === 'component' || kind === 'current_component') {
        const componentId = String(query?.componentId || query?.component_id || '').trim();
        value = surfacesRef.current?.[surfaceId]?.components?.[componentId]
          || Object.values(surfacesRef.current || {}).find((entry: any) => entry?.components?.[componentId])?.components?.[componentId];
      } else if (kind === 'surface_tree' || kind === 'current_surface_tree') {
        value = surfacesRef.current?.[surfaceId];
      } else {
        sendResult({ ok: false, error: `unknown_client_query_kind:${kind}` });
        return;
      }

      sendResult({ ok: true, value });
    } catch (error: any) {
      sendResult({ ok: false, error: String(error?.message || error || 'client_query_failed') });
    }
  }, [sendRaw]);

  const requestClientAuthContext = useCallback((reason = 'manual', opts?: { force?: boolean }) => {
    if (!isAuthenticatedRef.current) return false;
    if (!opts?.force && authSessionSyncPendingRef.current > 0) return false;
    const transport = transportRef.current;
    if (!transport || !transport.isOpen()) return false;

    const jwtKey = String(jwtRef.current || '__cookie__');
    const now = Date.now();
    if (
      lastAuthContextRequestRef.current.key === jwtKey
      && now - lastAuthContextRequestRef.current.at < 5000
    ) {
      return false;
    }

    const requestId = typeof crypto?.randomUUID === 'function'
      ? crypto.randomUUID()
      : `auth_ctx_${Date.now()}`;
    const sent = sendRaw({
      request_id: requestId,
      jwt: jwtRef.current || undefined,
      current_path: browserPathRef.current,
      userAction: {
        name: 'load_client_auth_context',
        context: {},
      },
    });
    if (sent) {
      lastAuthContextRequestRef.current = { key: jwtKey, at: now };
      debugLog('auth:context:requested', {
        reason,
        hasJwt: Boolean(jwtRef.current),
        jwtLength: jwtRef.current.length,
      });
    }
    return sent;
  }, [sendRaw]);

  const requestTokenRefresh = useCallback(() => {
    clearTokenRefreshTimer();
    if (!isAuthenticatedRef.current) return;

    const transport = transportRef.current;
    if (!transport || !transport.isOpen()) {
      tokenRefreshTimerRef.current = window.setTimeout(requestTokenRefresh, TOKEN_REFRESH_RETRY_SECONDS * 1000);
      return;
    }

    const requestId = typeof crypto?.randomUUID === 'function'
      ? crypto.randomUUID()
      : `refresh_${Date.now()}`;

    sendRaw({
      request_id: requestId,
      jwt: jwtRef.current || undefined,
      current_path: browserPathRef.current,
      userAction: {
        name: 'refresh_token',
        context: {},
      },
    });

    // Keep a retry armed; a fresh JWT from inbound messages will re-schedule
    // using the new token expiry.
    tokenRefreshTimerRef.current = window.setTimeout(requestTokenRefresh, TOKEN_REFRESH_RETRY_SECONDS * 1000);
  }, [clearTokenRefreshTimer, sendRaw]);

  const scheduleTokenRefresh = useCallback((token?: string) => {
    clearTokenRefreshTimer();
    if (!isAuthenticatedRef.current) return;

    const normalizedToken = typeof token === 'string' ? token.trim() : '';
    if (normalizedToken) {
      tokenExpiryRef.current = decodeJwtExpiry(normalizedToken);
    }

    const now = Math.floor(Date.now() / 1000);
    const exp = tokenExpiryRef.current;
    const delaySeconds = exp == null
      ? TOKEN_REFRESH_FALLBACK_SECONDS
      : Math.max(1, exp - now - TOKEN_REFRESH_LEAD_SECONDS);
    const delayMs = Math.max(TOKEN_REFRESH_MIN_DELAY_MS, delaySeconds * 1000);
    tokenRefreshTimerRef.current = window.setTimeout(requestTokenRefresh, delayMs);
  }, [clearTokenRefreshTimer, requestTokenRefresh]);

  const syncAuthCookie = useCallback(async (token: string) => {
    const baseUrl = getCoreHttpBaseUrl();

    if (token) {
      const response = await fetch(`${baseUrl}/auth/session`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jwt: token }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) {
          clearClientAuthSession(payload);
          return;
        }
        throw new Error(String(payload?.error || 'auth_cookie_sync_failed'));
      }
      applyAuthState(payload);
      scheduleTokenRefresh(token);
      if (transportKind !== 'tauri-ipc' && !authSessionCookieReconnectDoneRef.current) {
        authSessionCookieReconnectDoneRef.current = true;
        reconnect();
      }
      return;
    }

    await fetch(`${baseUrl}/auth/session`, {
      method: 'DELETE',
      credentials: 'include',
    }).catch(() => undefined);
    applyAuthState(null);
    persistJwt('');
    authSessionCookieReconnectDoneRef.current = false;
    clearTokenRefreshTimer();
    reconnect();
  }, [applyAuthState, clearClientAuthSession, clearTokenRefreshTimer, persistJwt, reconnect, scheduleTokenRefresh, transportKind]);

  const enqueueAuthSessionSync = useCallback((token: string, reason = 'inbound_jwt') => {
    const normalizedToken = String(token || '');
    const version = authSessionSyncVersionRef.current + 1;
    authSessionSyncVersionRef.current = version;
    authSessionSyncPendingRef.current += 1;

    authSessionSyncQueueRef.current = authSessionSyncQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        await syncAuthCookie(normalizedToken);
        if (normalizedToken && version === authSessionSyncVersionRef.current) {
          requestClientAuthContext(`${reason}:after_session_sync`, { force: true });
        }
      })
      .catch((error) => {
        console.error('[useA2UI] Unable to sync auth cookie', error);
      })
      .finally(() => {
        authSessionSyncPendingRef.current = Math.max(0, authSessionSyncPendingRef.current - 1);
      });
  }, [requestClientAuthContext, syncAuthCookie]);

  const loadAuthSession = useCallback(async () => {
    const response = await fetch(`${getCoreHttpBaseUrl()}/auth/session`, {
      credentials: 'include',
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok && response.status === 401) {
      clearClientAuthSession(payload);
      return;
    }
    if (typeof payload?.jwt === 'string') {
      persistJwt(payload.jwt);
    }
    applyAuthState(payload);
    scheduleTokenRefresh(typeof payload?.jwt === 'string' ? payload.jwt : undefined);
  }, [applyAuthState, clearClientAuthSession, persistJwt, scheduleTokenRefresh]);

  const releasePendingAction = useCallback((requestId: any) => {
    const rid = String(requestId || '').trim();
    if (!rid) return;
    const timer = pendingTimeoutsRef.current[rid];
    if (timer != null) {
      window.clearTimeout(timer);
      const nextTimeouts = { ...pendingTimeoutsRef.current };
      delete nextTimeouts[rid];
      pendingTimeoutsRef.current = nextTimeouts;
    }
    const actionName = pendingRequestsRef.current[rid];
    if (!actionName) return;
    const nextRequests = { ...pendingRequestsRef.current };
    delete nextRequests[rid];
    pendingRequestsRef.current = nextRequests;

    const nextCount = Math.max(0, (pendingActionsRef.current[actionName] || 0) - 1);
    const nextPending = { ...pendingActionsRef.current };
    if (nextCount <= 0) {
      delete nextPending[actionName];
    } else {
      nextPending[actionName] = nextCount;
    }
    pendingActionsRef.current = nextPending;
    setPendingActions(nextPending);
  }, []);

  const incrementPendingAction = useCallback((actionName: string, requestId: string): boolean => {
    const key = String(actionName || '').trim();
    const rid = String(requestId || '').trim();
    if (!key || !rid) return true;
    if ((pendingActionsRef.current[key] || 0) > 0) {
      debugLog('action:lock:skip', { actionName: key, requestId: rid });
      return false;
    }
    pendingRequestsRef.current = { ...pendingRequestsRef.current, [rid]: key };
    pendingActionsRef.current = {
      ...pendingActionsRef.current,
      [key]: (pendingActionsRef.current[key] || 0) + 1,
    };
    if (pendingTimeoutsRef.current[rid] != null) {
      window.clearTimeout(pendingTimeoutsRef.current[rid]);
    }
    pendingTimeoutsRef.current = {
      ...pendingTimeoutsRef.current,
      [rid]: window.setTimeout(() => {
        debugLog('action:lock:timeout', { actionName: key, requestId: rid });
        releasePendingAction(rid);
      }, PENDING_ACTION_TIMEOUT_MS),
    };
    setPendingActions(pendingActionsRef.current);
    return true;
  }, [releasePendingAction]);

  const clearPendingActions = useCallback(() => {
    Object.values(pendingTimeoutsRef.current).forEach((timer) => window.clearTimeout(timer));
    pendingTimeoutsRef.current = {};
    pendingRequestsRef.current = {};
    pendingActionsRef.current = {};
    setNotificationCount(0);
    setPendingActions({});
  }, []);

  const processPropertyUpdate = useCallback((update: any) => {
    const normalized = normalizePropertyUpdate(update);
    if (!normalized) {
      debugLog('property:update:ignored', summarizeDebugMessage(update));
      return;
    }
    debugLog('property:update', summarizeDebugMessage(normalized));
    setSurfaces((prev) => {
      const next = applyPropertyUpdateToSurfaces(prev, normalized);
      if (next === prev) {
        debugLog(
          'property:update:noop',
          summarizeDebugMessage(normalized),
          Object.fromEntries(
            Object.entries(prev).map(([sid, surface]) => [sid, Object.keys(surface?.components || {}).length]),
          ),
        );
      } else {
        debugLog('property:update:applied', {
          componentId: normalized.componentId,
          propertyName: normalized.propertyName,
          action: normalized.action,
          surfaceId: normalized.surfaceId,
        });
      }
      return next;
    });
  }, []);

  const handleMessageData = useCallback((msg: any) => {
    if (!msg || typeof msg !== 'object') return;
    debugLog('inbound:dispatch', summarizeDebugMessage(msg));
    collectInboundRequestIds(msg).forEach((requestId) => releasePendingAction(requestId));

    if (typeof msg.jwt === 'string' && msg.jwt !== jwtRef.current) {
      persistJwt(msg.jwt);
      if (msg.jwt) {
        scheduleTokenRefresh(msg.jwt);
      } else {
        clearTokenRefreshTimer();
      }
      enqueueAuthSessionSync(msg.jwt, 'msg.jwt');
    }

    if (Array.isArray(msg.messages)) {
      msg.messages.forEach((entry: any) => handleMessageData(entry));
      return;
    }
    if (msg.type === 'ui_messages' && Array.isArray(msg.messages)) {
      msg.messages.forEach((entry: any) => handleMessageData(entry));
      return;
    }
    if (msg.message && typeof msg.message === 'object') {
      handleMessageData(msg.message);
      return;
    }

    if (msg.clientQuery || msg.client_query) {
      respondToClientQuery(msg.clientQuery || msg.client_query);
      return;
    }

    if (msg.type === 'error' && String(msg.error || '').startsWith('stream_binding_')) {
      // eslint-disable-next-line no-console
      console.warn('[StreamBinding]', msg.error, summarizeDebugMessage(msg));
      return;
    }

    if (msg.current_path !== undefined) {
      const nextPath = routeFromCurrentPathMessage(msg.current_path);

      setStateModel((prev) => setCurrentPath(prev, nextPath));

      /*
      const currentBrowserPath = normalizeRoute(`${window.location.pathname || '/'}${window.location.search || ''}`);
      if (currentBrowserPath !== nextPath) {
        if (!hasSyncedBrowserPathRef.current) {
          window.history.replaceState({}, '', nextPath);
          hasSyncedBrowserPathRef.current = true;
        } else {
          window.history.pushState({}, '', nextPath);
        }
      }*/
      const currentBrowserPath = readBrowserRoute();
      if (currentBrowserPath !== nextPath) {
        writeBrowserRoute(nextPath, !hasSyncedBrowserPathRef.current);
        hasSyncedBrowserPathRef.current = true;
      }
      browserPathRef.current = nextPath;
    }

    if (msg.propertyUpdate || msg.property_update) {
      processPropertyUpdate(msg.propertyUpdate || msg.property_update);
      return;
    }

    if (msg.surfaceUpdate || msg.surface_update) {
      const payload = msg.surfaceUpdate || msg.surface_update;
      setSurfaces((prev) => applySurfaceUpdate(prev, payload));
      return;
    }

    if (msg.beginRendering || msg.begin_rendering) {
      const payload = msg.beginRendering || msg.begin_rendering;
      setSurfaces((prev) => applyBeginRendering(prev, payload));
      return;
    }

    if (msg.dataModelUpdate || msg.data_model_update) {
      const payload = msg.dataModelUpdate || msg.data_model_update;
      setDataModel((prev) => applyDataModelUpdate(prev, payload));
      return;
    }

    if (msg.deleteSurface || msg.delete_surface) {
      const payload = msg.deleteSurface || msg.delete_surface;
      setSurfaces((prev) => applyDeleteSurface(prev, payload));
      setDataModel((prev) => applyDeleteSurface(prev, payload));
      return;
    }

    if (msg.stateUpdate) {
      const values = msg.stateUpdate.values || {};
      const scope = String(msg.stateUpdate.scope || 'global').toLowerCase();
      if (values && typeof values === 'object') {
        setStateModel((prev) => updateClientState(prev, values, scope === 'page' ? 'page' : 'global'));
      }
      return;
    }

    if (msg.statePatch || msg.state_patch) {
      const payload = msg.statePatch || msg.state_patch;
      if (payload && typeof payload === 'object') {
        setStateModel((prev) => patchClientState(prev, payload));
      }
      return;
    }

    if (msg.windowAction) {
      const op = msg.windowAction.op;
      if (op === 'center') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
      if (op === 'copy_to_clipboard') {
        const text = String(msg.windowAction.text || '');
        if (text) {
          void navigator.clipboard.writeText(text);
          toast.success('Copiato negli appunti');
        }
      }
      if (op === 'open_url') {
        const rawUrl = String(msg.windowAction.url || '');
        const resolvedUrl = resolveWindowActionUrl(rawUrl);
        if (!resolvedUrl) return;

        if (Boolean(msg.windowAction.download)) {
          const filename = String(msg.windowAction.filename || '').trim();
        void downloadWindowActionUrl(resolvedUrl, filename).catch(() => {
            const fallback = document.createElement('a');
            fallback.href = resolvedUrl;
            if (filename) fallback.download = filename;
            fallback.rel = 'noreferrer';
            fallback.click();
          });
          return;
        }

        const link = document.createElement('a');
        link.href = resolvedUrl;
        link.target = '_blank';
        link.rel = 'noreferrer';
        link.click();
      }
      return;
    }

    const notificationsUpdate = msg.notificationsUpdate || (msg.type === 'notifications_update' ? msg.notificationsUpdate : null);
    if (notificationsUpdate) {
      const pendingCount = Math.max(0, parseInt(String(notificationsUpdate.count ?? 0), 10) || 0);
      setNotificationCount(pendingCount);
      setStateModel((prev) => updateClientState(prev, {
        '/core/notifications/pending_count': pendingCount,
      }, 'global'));
      return;
    }

    const externalAccessApproved = msg.externalAccessApproved || (msg.type === 'external_access_approved' ? msg.externalAccessApproved : null);
    if (externalAccessApproved) {
      recordExternalAccessDecisionAck({
        decision: 'permanent',
        module_name: String(externalAccessApproved.module_name || ''),
        target: String(externalAccessApproved.target || ''),
      });
      return;
    }

    const bgStarted = msg.backgroundTaskStarted || msg.background_task_started;
    if (bgStarted) {
      const taskId = String(bgStarted.taskId ?? bgStarted.task_id ?? '');
      if (!taskId) return;
      const label = String(bgStarted.label ?? '');
      const plugin = String(bgStarted.plugin ?? '');
      setBackgroundTasks((prev) => ({
        ...prev,
        [taskId]: { taskId, label, plugin, status: 'started', progress: 0 },
      }));
      setStateModel((prev) => updateClientState(prev, {
        [`background_tasks/${taskId}`]: { taskId, label, status: 'started', progress: 0 },
      }, 'global'));
      dispatchBackgroundTaskEvent('on_started', 'backgroundTaskStarted', bgStarted);
      return;
    }

    const bgProgress = msg.backgroundTaskProgress || msg.background_task_progress;
    if (bgProgress) {
      const taskId = String(bgProgress.taskId ?? bgProgress.task_id ?? '');
      if (!taskId) return;
      const progress = Number(bgProgress.progress ?? 0);
      const label = typeof bgProgress.label === 'string' ? bgProgress.label : '';
      setBackgroundTasks((prev) => {
        const existing = prev[taskId];
        if (!existing) return prev;
        return {
          ...prev,
          [taskId]: {
            ...existing,
            status: 'running',
            progress,
            ...(label ? { label } : {}),
          },
        };
      });
      setStateModel((prev) => updateClientState(prev, {
        [`background_tasks/${taskId}/status`]: 'running',
        [`background_tasks/${taskId}/progress`]: progress,
        ...(label ? { [`background_tasks/${taskId}/label`]: label } : {}),
      }, 'global'));
      dispatchBackgroundTaskEvent('on_progress', 'backgroundTaskProgress', bgProgress);
      return;
    }

    const bgCompleted = msg.backgroundTaskCompleted || msg.background_task_completed;
    if (bgCompleted) {
      const taskId = String(bgCompleted.taskId ?? bgCompleted.task_id ?? '');
      if (!taskId) return;
      const label = typeof bgCompleted.label === 'string' ? bgCompleted.label : '';
      const result = bgCompleted.result;
      setBackgroundTasks((prev) => {
        const existing = prev[taskId];
        if (!existing) return prev;
        return {
          ...prev,
          [taskId]: {
            ...existing,
            status: 'completed',
            progress: 1,
            result,
            ...(label ? { label } : {}),
          },
        };
      });
      setStateModel((prev) => updateClientState(prev, {
        [`background_tasks/${taskId}/status`]: 'completed',
        [`background_tasks/${taskId}/progress`]: 1,
        [`background_tasks/${taskId}/result`]: result,
        ...(label ? { [`background_tasks/${taskId}/label`]: label } : {}),
      }, 'global'));
      dispatchBackgroundTaskEvent('on_completed', 'backgroundTaskCompleted', bgCompleted);
      dispatchBackgroundTaskEvent('on_finish', 'backgroundTaskCompleted', bgCompleted);
      return;
    }

    const bgError = msg.backgroundTaskError || msg.background_task_error;
    if (bgError) {
      const taskId = String(bgError.taskId ?? bgError.task_id ?? '');
      if (!taskId) return;
      const label = typeof bgError.label === 'string' ? bgError.label : '';
      const error = bgError.error;
      setBackgroundTasks((prev) => {
        const existing = prev[taskId];
        if (!existing) return prev;
        return {
          ...prev,
          [taskId]: {
            ...existing,
            status: 'failed',
            error,
            ...(label ? { label } : {}),
          },
        };
      });
      setStateModel((prev) => updateClientState(prev, {
        [`background_tasks/${taskId}/status`]: 'failed',
        [`background_tasks/${taskId}/error`]: error,
        ...(label ? { [`background_tasks/${taskId}/label`]: label } : {}),
      }, 'global'));
      dispatchBackgroundTaskEvent('on_error', 'backgroundTaskError', bgError);
      return;
    }

    const bgConfirmation = msg.backgroundTaskConfirmation || msg.background_task_confirmation;
    if (bgConfirmation) {
      const taskId = String(bgConfirmation.taskId ?? bgConfirmation.task_id ?? '');
      if (!taskId) return;
      const label = String(bgConfirmation.label ?? '');
      const surfaceId = String(bgConfirmation.surfaceId ?? bgConfirmation.surface_id ?? '');
      const components = Array.isArray(bgConfirmation.components) ? bgConfirmation.components : [];

      setBackgroundTasks((prev) => {
        const existing = prev[taskId] || { taskId, label, plugin: '', status: 'started', progress: 0 };
        return {
          ...prev,
          [taskId]: {
            ...existing,
            status: 'waiting_confirmation',
            label,
            confirmSurfaceId: surfaceId,
            confirmComponents: components,
          },
        };
      });

      if (surfaceId && components.length > 0) {
        const nextComponents: Record<string, Component> = {};
        components.forEach((c: Component) => {
          if (c?.id) nextComponents[c.id] = c;
        });

        setSurfaces((prev) => ({
          ...prev,
          [surfaceId]: {
            components: nextComponents,
            rootId: components[0]?.id,
          },
        }));
      }
      dispatchBackgroundTaskEvent('on_confirmation', 'backgroundTaskConfirmation', bgConfirmation);
      return;
    }

    const bgUpdate = msg.backgroundTaskUpdate || msg.background_task_update;
    if (bgUpdate) {
      const taskId = String(bgUpdate.taskId ?? bgUpdate.task_id ?? '');
      if (!taskId) return;
      setBackgroundTasks((prev) => {
        const existing = prev[taskId] || { taskId, label: '', plugin: '', status: 'started', progress: 0 };
        return {
          ...prev,
          [taskId]: {
            ...existing,
            ...bgUpdate,
          },
        };
      });
      setStateModel((prev) => {
        const existing = readClientStateValue(prev, 'global', `background_tasks/${taskId}`);
        return updateClientState(prev, {
          [`background_tasks/${taskId}`]: {
            ...(existing && typeof existing === 'object' ? existing : {}),
            ...bgUpdate,
          },
        }, 'global');
      });
      dispatchBackgroundTaskEvent('on_update', 'backgroundTaskUpdate', bgUpdate);
      return;
    }

    const eventNotification = msg.eventNotification || msg.event_notification;
    if (eventNotification) {
      dispatchBackgroundTaskEvent('on_event_notification', 'eventNotification', eventNotification);
      const { text, title, kind, variant } = eventNotification;
      const messageText = text || title || '';
      if (!messageText) return;

      const type = (variant || kind || 'info').toLowerCase();
      
      switch (type) {
        case 'success':
          toast.success(messageText);
          break;
        case 'error':
        case 'danger':
          toast.error(messageText);
          break;
        case 'warning':
          toast.warning(messageText);
          break;
        case 'info':
          toast.info(messageText);
          break;
        default:
          toast(messageText);
          break;
      }
      return;
    }

    if (msg.type === 'hot_reload') {
      sendRaw({
        type: 'init',
        jwt: jwtRef.current || undefined,
      });
    }
  }, [
    clearTokenRefreshTimer,
    enqueueAuthSessionSync,
    persistJwt,
    releasePendingAction,
    respondToClientQuery,
    scheduleTokenRefresh,
    sendRaw,
  ]);

  useEffect(() => {
    runtimeRef.current?.dispose();
    runtimeRef.current = createRuntimeComposition({
      messagePriority,
      processInboundMessage: handleMessageData,
      processPropertyUpdate,
    });
    return () => {
      runtimeRef.current?.dispose();
      runtimeRef.current = null;
    };
  }, [handleMessageData, processPropertyUpdate]);

  const connect = useCallback(() => {
    setConnectionState('connecting');
    debugLog('transport:connect', { transportKind, wsUrl, wsCodec });
    let transport: A2UITransport;
    const isCurrentTransport = () => transportRef.current === transport;
    transport = createA2UITransport({
      kind: transportKind,
      url: wsUrl,
      codec: wsCodec,
      debugLog,
      onOpen: () => {
        if (!isCurrentTransport()) return;
        setConnectionState('connected');
        reconnectDelayRef.current = 1000;
        scheduleTokenRefresh();

        //const currentBrowserPath = normalizeRoute(`${window.location.pathname || '/'}${window.location.search || ''}`);
        const currentBrowserPath = readBrowserRoute();
        browserPathRef.current = currentBrowserPath;

        sendRaw({
          type: 'init',
          jwt: jwtRef.current || undefined,
        });
        sendRaw({
          jwt: jwtRef.current || undefined,
          userAction: {
            name: 'modulesList',
            context: {},
          },
        });
        requestClientAuthContext('transport_open');

        if (currentBrowserPath !== '/') {
          sendRaw({
            jwt: jwtRef.current || undefined,
            userAction: {
              name: 'nav',
              context: { path: currentBrowserPath, client_surface_reset: true },
            },
          });
        }

        if (heartbeatTimerRef.current != null) {
          window.clearInterval(heartbeatTimerRef.current);
        }
        heartbeatTimerRef.current = window.setInterval(() => {
          const currentTransport = transportRef.current;
          if (!currentTransport || !currentTransport.isOpen()) return;
          sendRaw({ type: 'ping' });
        }, 20000);
      },
      onMessage: (msg) => {
        if (!isCurrentTransport()) return;
        debugLog('transport:message', msg);
        if (Array.isArray(msg)) {
          msg.forEach((item) => {
            if (item && typeof item === 'object') {
              collectInboundRequestIds(item).forEach((requestId) => releasePendingAction(requestId));
              runtimeRef.current?.inbound.enqueue(item);
            }
          });
        } else if (msg && typeof msg === 'object') {
          collectInboundRequestIds(msg).forEach((requestId) => releasePendingAction(requestId));
          runtimeRef.current?.inbound.enqueue(msg);
        }
      },
      onError: (error) => {
        if (!isCurrentTransport()) return;
        setConnectionState('disconnected');
        debugLog('transport:error', error);
        clearTokenRefreshTimer();
        if (heartbeatTimerRef.current != null) {
          window.clearInterval(heartbeatTimerRef.current);
          heartbeatTimerRef.current = null;
        }
        if (notificationPollTimerRef.current != null) {
          window.clearInterval(notificationPollTimerRef.current);
          notificationPollTimerRef.current = null;
        }
        clearPendingActions();
      },
      onClose: () => {
        if (!isCurrentTransport()) return;
        setConnectionState('disconnected');
        debugLog('transport:close');
        clearTokenRefreshTimer();
        if (heartbeatTimerRef.current != null) {
          window.clearInterval(heartbeatTimerRef.current);
          heartbeatTimerRef.current = null;
        }
        if (notificationPollTimerRef.current != null) {
          window.clearInterval(notificationPollTimerRef.current);
          notificationPollTimerRef.current = null;
        }
        clearPendingActions();
        if (reconnectTimerRef.current == null) {
          const delay = reconnectDelayRef.current;
          reconnectDelayRef.current = Math.min(delay * 2, 30000);
          reconnectTimerRef.current = window.setTimeout(() => {
            reconnectTimerRef.current = null;
            connect();
          }, delay);
        }
      },
    });
    transportRef.current = transport;
    transport.connect();
  }, [clearPendingActions, clearTokenRefreshTimer, requestClientAuthContext, scheduleTokenRefresh, sendRaw, transportKind, wsCodec, wsUrl]);

  useEffect(() => {
    let cancelled = false;
    void loadAuthSession()
      .catch((error) => {
        console.error('[useA2UI] Unable to load auth session', error);
      })
      .finally(() => {
        if (!cancelled) connect();
      });

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current != null) window.clearTimeout(reconnectTimerRef.current);
      if (heartbeatTimerRef.current != null) window.clearInterval(heartbeatTimerRef.current);
      if (notificationPollTimerRef.current != null) window.clearInterval(notificationPollTimerRef.current);
      clearTokenRefreshTimer();
      runtimeRef.current?.dispose();
      transportRef.current?.close();
      transportRef.current = null;
    };
  }, [clearTokenRefreshTimer, connect, loadAuthSession]);

  useEffect(() => {
    if (connectionState !== 'connected' || !isAuthenticatedRef.current) {
      if (notificationPollTimerRef.current != null) {
        window.clearInterval(notificationPollTimerRef.current);
        notificationPollTimerRef.current = null;
      }
      return;
    }

    const poll = () => {
      const currentTransport = transportRef.current;
      if (!currentTransport || !currentTransport.isOpen()) return;
      if (!isAuthenticatedRef.current) return;
      sendRaw({
        jwt: jwtRef.current || undefined,
        current_path: browserPathRef.current,
        userAction: { name: 'get_notifications_count', context: {} },
      });
    };

    // Immediate poll on connection/auth
    poll();

    notificationPollTimerRef.current = window.setInterval(poll, NOTIFICATION_POLL_INTERVAL_MS);

    return () => {
      if (notificationPollTimerRef.current != null) {
        window.clearInterval(notificationPollTimerRef.current);
        notificationPollTimerRef.current = null;
      }
    };
  }, [connectionState, userRole, sendRaw]);

  useEffect(() => {
    const onPopState = () => {
      const nextPath = readBrowserRoute()// normalizeRoute(`${window.location.pathname || '/'}${window.location.search || ''}`);
      browserPathRef.current = nextPath;
      hasSyncedBrowserPathRef.current = true;
      sendRaw({
        jwt: jwtRef.current || undefined,
        current_path: nextPath,
        userAction: {
          name: 'nav',
          context: { path: nextPath },
        },
      });
    };

    window.addEventListener('popstate', onPopState);
    window.addEventListener('hashchange', onPopState);
    return () => {
      window.removeEventListener('popstate', onPopState)
      window.removeEventListener('hashchange', onPopState)
    };
  }, [sendRaw]);

  const setInput = useCallback((id: string, value: any) => {
    inputsRef.current = { ...inputsRef.current, [id]: value };
    setInputs((prev) => ({ ...prev, [id]: value }));
  }, []);

  const sendAction = useCallback(async (actionName: string, context: any = {}, surfaceId = 'main', componentId = '') => {
    if (actionName === '__stream_binding.subscribe') {
      sendRaw({
        jwt: jwtRef.current || undefined,
        streamBindingSubscribe: sanitizeOutboundValue(context),
      });
      return;
    }
    if (actionName === '__stream_binding.unsubscribe') {
      sendRaw({
        jwt: jwtRef.current || undefined,
        streamBindingUnsubscribe: sanitizeOutboundValue(context),
      });
      return;
    }

    const requestId = crypto.randomUUID();
    const { cleanContext, meta } = extractClientActionMeta(context);
    const includeInputsForAuth = shouldAttachInputsForAction(actionName, cleanContext);
    let collectedInputs = meta.collectInputIds
      ? Object.fromEntries(
        meta.collectInputIds
          .filter((key) => Object.prototype.hasOwnProperty.call(inputsRef.current, key))
          .map((key) => [key, inputsRef.current[key]]),
      )
      : (includeInputsForAuth ? { ...inputsRef.current } : { ...inputsRef.current });

    try {
      if (meta.uploadInputIds && meta.uploadInputIds.length > 0) {
        const moduleName = inferModuleNameFromAction(actionName);
        const uploadedEntries = await Promise.all(
          meta.uploadInputIds.map(async (inputId) => {
            if (!Object.prototype.hasOwnProperty.call(inputsRef.current, inputId)) {
              throw new Error(`upload_input_id not found: ${inputId}`);
            }
            const currentValue = inputsRef.current[inputId];
            if (!Array.isArray(currentValue)) {
              throw new Error(`upload_input_id requires attachment array: ${inputId}`);
            }
            const uploaded = await materializeAttachmentUploads(currentValue, {
              moduleName,
              jwt: jwtRef.current || undefined,
            });
            inputsRef.current = { ...inputsRef.current, [inputId]: uploaded };
            setInputs((prev) => ({ ...prev, [inputId]: uploaded }));
            return [inputId, uploaded] as const;
          }),
        );
        collectedInputs = {
          ...collectedInputs,
          ...Object.fromEntries(uploadedEntries),
        };
      }
    } catch (uploadError) {
      // eslint-disable-next-line no-console
      console.error('[useA2UI] upload_input_id failed', uploadError);
      return;
    }

    const fullContext = {
      ...sanitizeOutboundValue(collectedInputs),
      ...sanitizeOutboundValue(cleanContext),
    };

    if (actionName === 'client.copy_to_clipboard') {
      const text = String(fullContext.text || '');
      if (text) {
        void navigator.clipboard.writeText(text);
        toast.success(`Copied: ${text}`);
      }
      return;
    }

    if (!incrementPendingAction(actionName, requestId)) {
      return;
    }
    const sent = sendRaw({
      request_id: requestId,
      jwt: jwtRef.current || undefined,
      current_path: browserPathRef.current,
      userAction: {
        name: actionName,
        surfaceId,
        sourceComponentId: componentId,
        timestamp: 'now',
        context: fullContext,
      },
    });
    if (!sent) {
      releasePendingAction(requestId);
      return;
    }

    const normalizedActionName = String(actionName || '').trim().toLowerCase();
    const isLogoutAction = normalizedActionName === 'logout' || normalizedActionName.endsWith('.logout');
    if (isLogoutAction) {
      enqueueAuthSessionSync('', 'sendAction.logout');
    }
  }, [enqueueAuthSessionSync, incrementPendingAction, releasePendingAction, sendRaw]);

  const sendTaskResponse = useCallback((taskId: string, response: any = {}) => {
    sendRaw({
      jwt: jwtRef.current || undefined,
      backgroundTaskResponse: { taskId, response },
    });
  }, [sendRaw]);

  const cancelTask = useCallback((taskId: string) => {
    sendRaw({
      jwt: jwtRef.current || undefined,
      backgroundTaskCancel: { taskId },
    });
  }, [sendRaw]);

  const closeSurface = useCallback((surfaceId: string) => {
    setSurfaces((prev) => applyDeleteSurface(prev, { surfaceId }));
    setDataModel((prev) => applyDeleteSurface(prev, { surfaceId }));
  }, []);

  return {
    surfaces,
    dataModel,
    stateModel,
    inputs,
    pendingActions,
    backgroundTasks,
    notificationCount,
    connectionState,
    userRole,
    userPermissions,
    sendAction,
    setInput,
    sendTaskResponse,
    cancelTask,
    closeSurface,
    getValue: (path: string, scope: 'auto' | 'page' | 'global' = 'auto') =>
      readClientStateValue(stateModel, scope, path),
  };
}
