import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Clipboard from 'expo-clipboard';
import { Alert } from 'react-native';
import { decode as atob } from 'base-64';
import { decodeWsMessage, encodeWsMessage, normalizeWsCodec, type WsCodec } from '../utils/wsCodec';
import { applyPropertyUpdateToSurfaces, normalizePropertyUpdate } from '../runtime/controllers/property_updates';
import {
  applyBeginRendering,
  applyDataModelUpdate,
  applyDeleteSurface,
  applySurfaceUpdate,
} from '../runtime/controllers/surfaces';
import { createRuntimeComposition } from '../runtime/composition';
import {
  inferModuleNameFromAction,
  materializeAttachmentUploads,
} from '../utils/uploads';

export type UseA2UIOptions = {
  url?: string;
  codec?: WsCodec | string;
};

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

type ClientActionMeta = {
  collectInputIds?: string[];
  uploadInputIds?: string[];
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

const PENDING_ACTION_TIMEOUT_MS = 15000;
const NOTIFICATION_POLL_INTERVAL_MS = 30000;
const TOKEN_REFRESH_LEAD_SECONDS = 60;
const TOKEN_REFRESH_RETRY_SECONDS = 30;
const TOKEN_REFRESH_FALLBACK_SECONDS = 300;
const TOKEN_REFRESH_MIN_DELAY_MS = 1000;
const DEFAULT_URL = 'ws://localhost:8000/ws';

const runtimeValuesEqual = (left: any, right: any): boolean => {
  if (Object.is(left, right)) return true;
  try {
    return JSON.stringify(left) === JSON.stringify(right);
  } catch {
    return false;
  }
};

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

  if (data.windowAction || data.window_action || data.stateUpdate || data.state_update || data.statePatch || data.state_patch) return 1;
  if (
    data.collectionAppend ||
    data.collectionPrepend ||
    data.collectionRemove ||
    data.collectionReplace ||
    data.collection_append ||
    data.collection_prepend ||
    data.collection_remove ||
    data.collection_replace
  ) return 2;
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

function deepCopy<T>(value: T): T {
  if (Array.isArray(value)) return value.map((entry) => deepCopy(entry)) as T;
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, any>).map(([key, entry]) => [key, deepCopy(entry)]),
    ) as T;
  }
  return value;
}

function getHttpBaseUrl(wsUrl: string): string {
  const raw = String(wsUrl || DEFAULT_URL);
  try {
    const parsed = new URL(raw);
    parsed.protocol = parsed.protocol === 'wss:' ? 'https:' : 'http:';
    parsed.pathname = '';
    parsed.search = '';
    parsed.hash = '';
    return parsed.toString().replace(/\/$/, '');
  } catch {
    return 'http://localhost:8000';
  }
}

function unflatten(obj: Record<string, any>, target: Record<string, any>): void {
  Object.entries(obj).forEach(([key, value]) => {
    const parts = key.replace(/^\//, '').split(/[./]/).filter(Boolean);
    let current = target;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const p = parts[i];
      if (!current[p] || typeof current[p] !== 'object') {
        current[p] = {};
      }
      current = current[p];
    }
    const last = parts[parts.length - 1];
    if (last) current[last] = value;
  });
}

function createRequestId(): string {
  const randomUuid = (globalThis as any)?.crypto?.randomUUID;
  if (typeof randomUuid === 'function') return randomUuid.call((globalThis as any).crypto);
  return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
}

function normalizeClientInputIds(raw: any): string[] | undefined {
  if (Array.isArray(raw)) {
    const values = raw.map((entry: any) => String(entry || '').trim()).filter(Boolean);
    return values.length > 0 ? values : undefined;
  }
  const single = String(raw || '').trim();
  return single ? [single] : undefined;
}

function extractClientActionMeta(context: any): { cleanContext: Record<string, any>; meta: ClientActionMeta } {
  if (!context || typeof context !== 'object' || Array.isArray(context)) {
    return { cleanContext: {}, meta: {} };
  }

  const cleanContext: Record<string, any> = { ...context };
  const uploadInputIds = normalizeClientInputIds(cleanContext.upload_input_ids ?? cleanContext.upload_input_id);
  delete cleanContext.upload_input_ids;
  delete cleanContext.upload_input_id;

  const rawMeta = cleanContext.__client__;
  delete cleanContext.__client__;

  if (!rawMeta || typeof rawMeta !== 'object' || Array.isArray(rawMeta)) {
    return { cleanContext, meta: { uploadInputIds } };
  }

  const collectInputIds = normalizeClientInputIds((rawMeta as any).collect_input_ids);
  return { cleanContext, meta: { collectInputIds, uploadInputIds } };
}

function sanitizeOutboundValue(value: any): any {
  if (Array.isArray(value)) return value.map((entry) => sanitizeOutboundValue(entry));
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, nested]) => [key, sanitizeOutboundValue(nested)]),
    );
  }
  return value;
}

function collectInboundRequestIds(message: any, result: Set<string> = new Set()): Set<string> {
  if (!message || typeof message !== 'object') return result;

  const directRequestId = String(message.request_id || message.requestId || '').trim();
  if (directRequestId) result.add(directRequestId);

  const nestedRequestId = String(message?.actionBusy?.requestId || '').trim();
  if (nestedRequestId) result.add(nestedRequestId);

  const bindingRequestId = String(message?.bindingActionResult?.requestId || '').trim();
  if (bindingRequestId) result.add(bindingRequestId);

  if (Array.isArray(message.messages)) {
    message.messages.forEach((entry: any) => collectInboundRequestIds(entry, result));
  }
  if (message.message && typeof message.message === 'object') {
    collectInboundRequestIds(message.message, result);
  }

  return result;
}

function routeFromCurrentPathMessage(currentPath: any): string {
  if (typeof currentPath === 'string') return currentPath.startsWith('/') ? currentPath : `/${currentPath}`;
  const appName = String(currentPath?.app_name || currentPath?.appName || '').replace(/^\/+|\/+$/g, '');
  const pagePath = String(currentPath?.page_path || currentPath?.pagePath || '').replace(/^\/+|\/+$/g, '');
  const joined = [appName, pagePath].filter(Boolean).join('/');
  return joined ? `/${joined}` : '/';
}

function normalizeStateSegments(path: string): string[] {
  return String(path || '').trim().replace(/^\//, '').split(/[./]/).filter(Boolean);
}

function getDeepStateValue(target: any, path: string): any {
  const segments = normalizeStateSegments(path);
  if (!segments.length) return target;
  return segments.reduce((cursor: any, key) => (cursor == null || typeof cursor !== 'object' ? undefined : cursor[key]), target);
}

function setDeepStateValue(target: Record<string, any>, path: string, value: any): Record<string, any> {
  const next = { ...target };
  const segments = normalizeStateSegments(path);
  if (segments.length === 0) return next;
  let cursor: any = next;
  for (let i = 0; i < segments.length - 1; i += 1) {
    const key = segments[i];
    cursor[key] = cursor[key] && typeof cursor[key] === 'object' ? { ...cursor[key] } : {};
    cursor = cursor[key];
  }
  cursor[segments[segments.length - 1]] = value;
  return next;
}

function collectionItems(value: any): any[] {
  return Array.isArray(value) ? value.map((entry) => deepCopy(entry)) : [deepCopy(value)];
}

function resolveCollectionIndex(items: any[], payload: any): number | null {
  if (typeof payload === 'number') return payload >= 0 && payload < items.length ? payload : null;
  if (payload && typeof payload === 'object') {
    if (typeof payload.index === 'number') return payload.index >= 0 && payload.index < items.length ? payload.index : null;
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

function patchStateCollection(items: any, action: string, value: any): any[] | null {
  const current = Array.isArray(items) ? items.map((entry) => deepCopy(entry)) : [];
  if (action === 'set') return Array.isArray(value) ? value.map((entry) => deepCopy(entry)) : [];
  if (action === 'append') return [...current, ...collectionItems(value)];
  if (action === 'prepend') return [...collectionItems(value), ...current];
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

function patchClientState(prev: Record<string, any>, payload: any): Record<string, any> {
  if (!payload || typeof payload !== 'object') return prev;
  const entries = Array.isArray(payload.patches) ? payload.patches : Array.isArray(payload.ops) ? payload.ops : [payload];
  return entries.reduce((state: Record<string, any>, patch: any) => {
    if (!patch || typeof patch !== 'object') return state;
    const path = patch.path ?? patch.key ?? patch.name;
    if (!path) return state;
    const scope = String(patch.scope || 'page').toLowerCase() === 'global' ? 'global' : 'page';
    const op = String(patch.op || patch.action || 'set').toLowerCase();
    const next = {
      ...state,
      global: deepCopy(state.global || {}),
      page: deepCopy(state.page || {}),
    };
    const target = scope === 'global' ? next.global : next.page;
    if (op === 'delete') {
      const parentPath = normalizeStateSegments(String(path)).slice(0, -1).join('/');
      const leaf = normalizeStateSegments(String(path)).pop();
      const parent = parentPath ? getDeepStateValue(target, parentPath) : target;
      if (parent && typeof parent === 'object' && leaf) delete parent[leaf];
      return next;
    }
    if (op === 'remove' || op === 'append' || op === 'prepend' || op === 'replace' || op === 'set') {
      const current = getDeepStateValue(target, String(path));
      const patched = patchStateCollection(current, op, patch.value);
      if (patched != null && (op !== 'set' || Array.isArray(current) || Array.isArray(patch.value))) {
        next[scope] = setDeepStateValue(target, String(path), patched);
        return next;
      }
    }
    next[scope] = setDeepStateValue(target, String(path), patch.value);
    return next;
  }, prev);
}

function updateStateValues(prev: Record<string, any>, values: Record<string, any>): Record<string, any> {
  const next = {
    ...prev,
    global: deepCopy(prev.global || {}),
    page: deepCopy(prev.page || {}),
  };
  return Object.entries(values).reduce((state, [path, value]) => ({
    ...state,
    global: setDeepStateValue(state.global || {}, path, value),
  }), next);
}

function resolveClientPath(source: any, path: any): any {
  if (!path) return source;
  const segments = String(path).replace(/^\//, '').split(/[./]/).filter(Boolean);
  return segments.reduce((cursor: any, key) => (cursor == null ? undefined : cursor[key]), source);
}

export function useA2UI(options?: UseA2UIOptions) {
  const [surfaces, setSurfaces] = useState<Record<string, Surface>>({ main: { components: {} } });
  const [dataModel, setDataModel] = useState<Record<string, Record<string, any>>>({ main: {} });
  const [stateModel, setStateModel] = useState<Record<string, any>>({ global: {}, page: {} });
  const [, setInputs] = useState<Record<string, any>>({});
  const [backgroundTasks, setBackgroundTasks] = useState<Record<string, BackgroundTaskInfo>>({});
  const [connectionState, setConnectionState] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [jwt, setJwt] = useState<string>('');
  const [userRole, setUserRole] = useState('Guest');
  const [userPermissions, setUserPermissions] = useState<string[]>([]);
  const [pendingActions, setPendingActions] = useState<Record<string, number>>({});

  const wsRef = useRef<WebSocket | null>(null);
  const runtimeRef = useRef<any>(null);
  const heartbeatTimerRef = useRef<any>(null);
  const reconnectTimerRef = useRef<any>(null);
  const notificationPollTimerRef = useRef<any>(null);
  const tokenRefreshTimerRef = useRef<any>(null);
  const tokenExpiryRef = useRef<number | null>(null);
  const isAuthenticatedRef = useRef<boolean>(false);
  const authSessionSyncQueueRef = useRef<Promise<void>>(Promise.resolve());
  const authSessionSyncVersionRef = useRef<number>(0);
  const jwtRef = useRef(jwt);
  const surfacesRef = useRef<Record<string, Surface>>({ main: { components: {} } });
  const stateModelRef = useRef<Record<string, any>>({ global: {}, page: {} });
  const pendingActionsRef = useRef<Record<string, number>>({});
  const pendingRequestsRef = useRef<Record<string, string>>({});
  const pendingTimeoutsRef = useRef<Record<string, any>>({});
  const dataModelRef = useRef<Record<string, Record<string, any>>>({ main: {} });
  const inputsRef = useRef<Record<string, any>>({});

  const wsCodec = useMemo(() => normalizeWsCodec(options?.codec || 'json'), [options?.codec]);
  const wsUrl = useMemo(() => {
    const base = options?.url || DEFAULT_URL;
    const glue = base.includes('?') ? '&' : '?';
    return `${base}${glue}codec=${encodeURIComponent(wsCodec)}`;
  }, [options?.url, wsCodec]);
  const httpBaseUrl = useMemo(() => getHttpBaseUrl(wsUrl), [wsUrl]);

  const sendRaw = useCallback((payload: any) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;

    const outbound = jwtRef.current && payload && typeof payload === 'object' && !Array.isArray(payload) && payload.jwt === undefined
      ? { ...payload, jwt: jwtRef.current }
      : payload;
    encodeWsMessage(outbound, wsCodec).then((encoded) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(encoded.payload);
      }
    }).catch((err) => {
      console.error('[useA2UI] Failed to encode message', err);
    });
    return true;
  }, [wsCodec]);

  const clearTokenRefreshTimer = useCallback(() => {
    if (tokenRefreshTimerRef.current != null) {
      clearTimeout(tokenRefreshTimerRef.current);
      tokenRefreshTimerRef.current = null;
    }
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
    setUserRole(authenticated ? role : 'Guest');
    setUserPermissions(authenticated ? permissions : []);
    const userValue = payload?.user && typeof payload.user === 'object'
      ? payload.user
      : hasUser
        ? { id: user }
        : null;
    setStateModel((prev) => {
      const next = updateStateValues(prev, {
        '/auth/authenticated': authenticated,
        '/auth/user': authenticated ? userValue : null,
        '/auth/role': authenticated ? role : 'Guest',
        '/auth/permissions': authenticated ? permissions : [],
        '/auth/permissions_loaded': authenticated ? permissionsLoaded : false,
      });
      stateModelRef.current = next;
      return next;
    });
  }, []);

  const persistJwt = useCallback((token: string) => {
    jwtRef.current = token;
    setJwt(token);
    if (token) {
      AsyncStorage.setItem('democrai_jwt', token).catch(() => undefined);
      tokenExpiryRef.current = decodeJwtExpiry(token);
      const claims = decodeJwtClaims(token);
      setUserRole(claims.role);
      setUserPermissions(claims.permissions);
      isAuthenticatedRef.current = true;
      return;
    }
    AsyncStorage.removeItem('democrai_jwt').catch(() => undefined);
    tokenExpiryRef.current = null;
    isAuthenticatedRef.current = false;
    setUserRole('Guest');
    setUserPermissions([]);
  }, []);

  const requestClientAuthContext = useCallback((reason = 'manual') => {
    if (!isAuthenticatedRef.current) return false;
    const requestId = createRequestId();
    return sendRaw({
      request_id: requestId,
      jwt: jwtRef.current || undefined,
      current_path: stateModelRef.current.current_path || stateModelRef.current.global?.current_path || '/',
      userAction: {
        name: 'load_client_auth_context',
        context: { reason },
      },
    });
  }, [sendRaw]);

  const requestTokenRefresh = useCallback(() => {
    clearTokenRefreshTimer();
    if (!isAuthenticatedRef.current) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      tokenRefreshTimerRef.current = setTimeout(requestTokenRefresh, TOKEN_REFRESH_RETRY_SECONDS * 1000);
      return;
    }
    sendRaw({
      request_id: createRequestId(),
      jwt: jwtRef.current || undefined,
      current_path: stateModelRef.current.current_path || stateModelRef.current.global?.current_path || '/',
      userAction: {
        name: 'refresh_token',
        context: {},
      },
    });
    tokenRefreshTimerRef.current = setTimeout(requestTokenRefresh, TOKEN_REFRESH_RETRY_SECONDS * 1000);
  }, [clearTokenRefreshTimer, sendRaw]);

  const scheduleTokenRefresh = useCallback((token?: string) => {
    clearTokenRefreshTimer();
    if (!isAuthenticatedRef.current) return;
    const normalizedToken = typeof token === 'string' ? token.trim() : '';
    if (normalizedToken) tokenExpiryRef.current = decodeJwtExpiry(normalizedToken);
    const now = Math.floor(Date.now() / 1000);
    const exp = tokenExpiryRef.current;
    const delaySeconds = exp == null
      ? TOKEN_REFRESH_FALLBACK_SECONDS
      : Math.max(1, exp - now - TOKEN_REFRESH_LEAD_SECONDS);
    tokenRefreshTimerRef.current = setTimeout(requestTokenRefresh, Math.max(TOKEN_REFRESH_MIN_DELAY_MS, delaySeconds * 1000));
  }, [clearTokenRefreshTimer, requestTokenRefresh]);

  const syncAuthSession = useCallback(async (token: string) => {
    if (token) {
      const response = await fetch(`${httpBaseUrl}/auth/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jwt: token }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401) {
          persistJwt('');
          applyAuthState(payload);
          clearTokenRefreshTimer();
          return;
        }
        throw new Error(String(payload?.error || 'auth_session_sync_failed'));
      }
      applyAuthState(payload);
      scheduleTokenRefresh(token);
      requestClientAuthContext('session_sync');
      return;
    }

    await fetch(`${httpBaseUrl}/auth/session`, { method: 'DELETE' }).catch(() => undefined);
    persistJwt('');
    applyAuthState(null);
    clearTokenRefreshTimer();
  }, [applyAuthState, clearTokenRefreshTimer, httpBaseUrl, persistJwt, requestClientAuthContext, scheduleTokenRefresh]);

  const enqueueAuthSessionSync = useCallback((token: string) => {
    const version = authSessionSyncVersionRef.current + 1;
    authSessionSyncVersionRef.current = version;
    authSessionSyncQueueRef.current = authSessionSyncQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        await syncAuthSession(String(token || ''));
        if (token && version === authSessionSyncVersionRef.current) {
          requestClientAuthContext('after_session_sync');
        }
      })
      .catch((error) => console.error('[useA2UI] Unable to sync auth session', error));
  }, [requestClientAuthContext, syncAuthSession]);

  const loadAuthSession = useCallback(async () => {
    const response = await fetch(`${httpBaseUrl}/auth/session`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) {
        persistJwt('');
        applyAuthState(payload);
      }
      return;
    }
    if (typeof payload?.jwt === 'string') persistJwt(payload.jwt);
    applyAuthState(payload);
    scheduleTokenRefresh(typeof payload?.jwt === 'string' ? payload.jwt : undefined);
  }, [applyAuthState, httpBaseUrl, persistJwt, scheduleTokenRefresh]);

  useEffect(() => {
    surfacesRef.current = surfaces;
  }, [surfaces]);

  useEffect(() => {
    dataModelRef.current = dataModel;
  }, [dataModel]);

  useEffect(() => {
    stateModelRef.current = stateModel;
  }, [stateModel]);

  const releasePendingAction = useCallback((requestId: string) => {
    const rid = String(requestId || '').trim();
    if (!rid) return;
    const timer = pendingTimeoutsRef.current[rid];
    if (timer != null) {
      clearTimeout(timer);
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
    if (nextCount <= 0) delete nextPending[actionName];
    else nextPending[actionName] = nextCount;
    pendingActionsRef.current = nextPending;
    setPendingActions(nextPending);
  }, []);

  const incrementPendingAction = useCallback((actionName: string, requestId: string): boolean => {
    const key = String(actionName || '').trim();
    const rid = String(requestId || '').trim();
    if (!key || !rid) return true;
    if ((pendingActionsRef.current[key] || 0) > 0) return false;

    pendingRequestsRef.current = { ...pendingRequestsRef.current, [rid]: key };
    pendingActionsRef.current = {
      ...pendingActionsRef.current,
      [key]: (pendingActionsRef.current[key] || 0) + 1,
    };
    pendingTimeoutsRef.current = {
      ...pendingTimeoutsRef.current,
      [rid]: setTimeout(() => releasePendingAction(rid), PENDING_ACTION_TIMEOUT_MS),
    };
    setPendingActions(pendingActionsRef.current);
    return true;
  }, [releasePendingAction]);

  const sendAction = useCallback(async (actionName: string, context: any = {}, surfaceId = 'main', componentId = '') => {
    const normalizedActionName = actionName === 'navigate' ? 'nav' : actionName;

    if (normalizedActionName === '__stream_binding.subscribe') {
      return sendRaw({ streamBindingSubscribe: sanitizeOutboundValue(context) });
    }
    if (normalizedActionName === '__stream_binding.unsubscribe') {
      return sendRaw({ streamBindingUnsubscribe: sanitizeOutboundValue(context) });
    }

    const requestId = createRequestId();
    const { cleanContext, meta } = extractClientActionMeta(context);
    const normalizedContext = actionName === 'navigate'
      ? { type: 'nav', ...cleanContext }
      : cleanContext;
    let collectedInputs = meta.collectInputIds
      ? Object.fromEntries(
        meta.collectInputIds
          .filter((key) => Object.prototype.hasOwnProperty.call(inputsRef.current, key))
          .map((key) => [key, inputsRef.current[key]]),
      )
      : { ...inputsRef.current };

    try {
      if (meta.uploadInputIds && meta.uploadInputIds.length > 0) {
        const moduleName = inferModuleNameFromAction(normalizedActionName);
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
      console.error('[useA2UI] upload_input_id failed', uploadError);
      return false;
    }

    const fullContext = {
      ...sanitizeOutboundValue(collectedInputs),
      ...sanitizeOutboundValue(normalizedContext),
    };

    if (normalizedActionName === 'client.copy_to_clipboard') {
      const text = String(fullContext.text ?? fullContext.value ?? '').trim();
      if (text) {
        void Clipboard.setStringAsync(text)
          .then(() => Alert.alert('', 'Copied to clipboard'))
          .catch(() => Alert.alert('', 'Copy failed'));
      }
      return true;
    }

    if (!incrementPendingAction(normalizedActionName, requestId)) return false;
    const sent = sendRaw({
      request_id: requestId,
      current_path: stateModelRef.current.current_path || stateModelRef.current.currentPath || stateModelRef.current.global?.current_path || '/',
      userAction: {
        name: normalizedActionName,
        surfaceId,
        sourceComponentId: componentId,
        timestamp: 'now',
        context: fullContext,
      },
    });
    if (!sent) releasePendingAction(requestId);
    return sent;
  }, [incrementPendingAction, releasePendingAction, sendRaw]);

  const processPropertyUpdate = useCallback((update: any) => {
    const normalized = normalizePropertyUpdate(update);
    if (!normalized) return;
    setSurfaces((prev) => applyPropertyUpdateToSurfaces(prev, normalized));
  }, []);

  const setInput = useCallback((id: string, value: any) => {
    if (runtimeValuesEqual(inputsRef.current[id], value)) {
      return;
    }
    inputsRef.current = { ...inputsRef.current, [id]: value };
    setInputs((prev) => ({ ...prev, [id]: value }));
  }, []);

  const closeSurface = useCallback((surfaceId: string) => {
    const sid = String(surfaceId || '').trim();
    if (!sid) return;
    const payload = { surface_id: sid };
    setSurfaces((prev) => applyDeleteSurface(prev, payload));
    setDataModel((prev) => applyDeleteSurface(prev, payload));
    sendRaw({ closeSurface: payload });
  }, [sendRaw]);

  const respondToClientQuery = useCallback((query: any) => {
    const requestId = String(query?.requestId || query?.request_id || '').trim();
    if (!requestId) return;

    const sendResult = (result: any) => {
      sendRaw({ clientQueryResult: { requestId, ...result } });
    };

    try {
      const kind = String(query?.kind || '').trim();
      const surfaceId = String(query?.surfaceId || query?.surface_id || 'main');
      let value: any;

      if (kind === 'data_value' || kind === 'current_data_value') {
        value = resolveClientPath(dataModelRef.current?.[surfaceId] || {}, query?.path);
      } else if (kind === 'store_value' || kind === 'current_store_value') {
        value = resolveClientPath(stateModelRef.current || {}, query?.path);
      } else if (kind === 'component_props' || kind === 'current_component_props') {
        const componentId = String(query?.componentId || query?.component_id || '').trim();
        const component = surfacesRef.current?.[surfaceId]?.components?.[componentId]
          || Object.values(surfacesRef.current || {}).find((entry: any) => entry?.components?.[componentId])?.components?.[componentId];
        const type = Object.keys(component?.component || {})[0];
        value = type ? component.component[type] : undefined;
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

  const handleMessageData = useCallback((msg: any) => {
    if (!msg || typeof msg !== 'object') return;
    console.log('[A2UI] Inbound:', Object.keys(msg));
    collectInboundRequestIds(msg).forEach((requestId) => releasePendingAction(requestId));

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

    // JWT can be delivered together with rendering/state payloads.
    // Process it before branches that may early-return.
    if (typeof msg.jwt === 'string' && msg.jwt !== jwtRef.current) {
      persistJwt(msg.jwt);
      if (msg.jwt) scheduleTokenRefresh(msg.jwt);
      else clearTokenRefreshTimer();
      enqueueAuthSessionSync(msg.jwt);
    }

    const eventNotification = msg.eventNotification || msg.event_notification;
    if (eventNotification) {
      setStateModel((prev) => ({
        ...prev,
        last_event_notification: eventNotification,
      }));
    }

    if (msg.type === 'hot_reload') {
      sendRaw({ type: 'init', jwt: jwtRef.current || undefined });
      return;
    }

    if (msg.current_path !== undefined) {
      const pathStr = routeFromCurrentPathMessage(msg.current_path);
      setStateModel((prev) => {
        const next = updateStateValues(prev, { '/current_path': pathStr });
        stateModelRef.current = next;
        return next;
      });
      return;
    }

    if (msg.propertyUpdate || msg.property_update) {
      processPropertyUpdate(msg.propertyUpdate || msg.property_update);
      return;
    }

    if (msg.collectionAppend || msg.collection_append) {
      processPropertyUpdate({
        ...(msg.collectionAppend || msg.collection_append),
        action: 'append',
      });
      return;
    }

    if (msg.collectionPrepend || msg.collection_prepend) {
      processPropertyUpdate({
        ...(msg.collectionPrepend || msg.collection_prepend),
        action: 'prepend',
      });
      return;
    }

    if (msg.collectionRemove || msg.collection_remove) {
      processPropertyUpdate({
        ...(msg.collectionRemove || msg.collection_remove),
        action: 'remove',
      });
      return;
    }

    if (msg.collectionReplace || msg.collection_replace) {
      processPropertyUpdate({
        ...(msg.collectionReplace || msg.collection_replace),
        action: 'replace',
      });
      return;
    }

    if (msg.surfaceUpdate || msg.surface_update) {
      setSurfaces((prev) => applySurfaceUpdate(prev, msg.surfaceUpdate || msg.surface_update));
      return;
    }

    if (msg.beginRendering || msg.begin_rendering) {
      setSurfaces((prev) => applyBeginRendering(prev, msg.beginRendering || msg.begin_rendering));
      return;
    }

    if (msg.deleteSurface || msg.delete_surface) {
      const payload = msg.deleteSurface || msg.delete_surface;
      setSurfaces((prev) => applyDeleteSurface(prev, payload));
      setDataModel((prev) => applyDeleteSurface(prev, payload));
      return;
    }

    if (msg.dataModelUpdate || msg.data_model_update) {
      const payload = msg.dataModelUpdate || msg.data_model_update;
      setDataModel((prev) => {
        const next = applyDataModelUpdate(prev, payload);
        dataModelRef.current = next;
        return next;
      });
      return;
    }

    if (msg.stateUpdate || msg.state_update) {
      const payload = msg.stateUpdate || msg.state_update;
      const values = payload.values || {};
      const scope = String(payload.scope || 'global').toLowerCase();
      if (values && typeof values === 'object') {
        setStateModel((prev) => {
          const next = {
            ...prev,
            global: deepCopy(prev.global || {}),
            page: deepCopy(prev.page || {}),
          };
          const targetScope = scope === 'page' ? next.page : next.global;
          unflatten(values, targetScope);
          stateModelRef.current = next;
          return next;
        });
      }
      return;
    }

    const notificationsUpdate = msg.notificationsUpdate || (msg.type === 'notifications_update' ? msg.notificationsUpdate : null);
    if (notificationsUpdate) {
      const pendingCount = Math.max(0, parseInt(String(notificationsUpdate.count ?? 0), 10) || 0);
      setStateModel((prev) => updateStateValues(prev, {
        '/core/notifications/pending_count': pendingCount,
      }));
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
      setStateModel((prev) => updateStateValues(prev, {
        [`background_tasks/${taskId}`]: { taskId, label, status: 'started', progress: 0 },
      }));
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
          [taskId]: { ...existing, status: 'running', progress, ...(label ? { label } : {}) },
        };
      });
      setStateModel((prev) => updateStateValues(prev, {
        [`background_tasks/${taskId}/status`]: 'running',
        [`background_tasks/${taskId}/progress`]: progress,
        ...(label ? { [`background_tasks/${taskId}/label`]: label } : {}),
      }));
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
          [taskId]: { ...existing, status: 'completed', progress: 1, result, ...(label ? { label } : {}) },
        };
      });
      setStateModel((prev) => updateStateValues(prev, {
        [`background_tasks/${taskId}/status`]: 'completed',
        [`background_tasks/${taskId}/progress`]: 1,
        [`background_tasks/${taskId}/result`]: result,
        ...(label ? { [`background_tasks/${taskId}/label`]: label } : {}),
      }));
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
          [taskId]: { ...existing, status: 'failed', error, ...(label ? { label } : {}) },
        };
      });
      setStateModel((prev) => updateStateValues(prev, {
        [`background_tasks/${taskId}/status`]: 'failed',
        [`background_tasks/${taskId}/error`]: error,
        ...(label ? { [`background_tasks/${taskId}/label`]: label } : {}),
      }));
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
          [surfaceId]: { components: nextComponents, rootId: components[0]?.id },
        }));
      }
      return;
    }

    const bgUpdate = msg.backgroundTaskUpdate || msg.background_task_update;
    if (bgUpdate) {
      const taskId = String(bgUpdate.taskId ?? bgUpdate.task_id ?? '');
      if (!taskId) return;
      setBackgroundTasks((prev) => {
        const existing = prev[taskId] || { taskId, label: '', plugin: '', status: 'started', progress: 0 };
        return { ...prev, [taskId]: { ...existing, ...bgUpdate } };
      });
      setStateModel((prev) => updateStateValues(prev, {
        [`background_tasks/${taskId}`]: {
          ...(resolveClientPath(prev, `background_tasks/${taskId}`) || {}),
          ...bgUpdate,
        },
      }));
      return;
    }

    if (msg.statePatch || msg.state_patch) {
      const payload = msg.statePatch || msg.state_patch;
      setStateModel((prev) => {
        const next = patchClientState(prev, payload);
        stateModelRef.current = next;
        return next;
      });
      return;
    }

  }, [
    clearTokenRefreshTimer,
    enqueueAuthSessionSync,
    persistJwt,
    processPropertyUpdate,
    releasePendingAction,
    respondToClientQuery,
    scheduleTokenRefresh,
    sendRaw,
    wsUrl,
  ]);

  useEffect(() => {
    runtimeRef.current?.dispose?.();
    runtimeRef.current = createRuntimeComposition({
      messagePriority,
      processInboundMessage: handleMessageData,
      processPropertyUpdate,
    });
    return () => {
      runtimeRef.current?.dispose?.();
      runtimeRef.current = null;
    };
  }, [handleMessageData, processPropertyUpdate]);

  useEffect(() => {
      let cancelled = false;
      const connect = () => {
        if (cancelled) return;
        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer';
        wsRef.current = ws;

      ws.onopen = () => {
        console.log('[A2UI] Connected to', wsUrl);
        setConnectionState('connected');
        scheduleTokenRefresh();
        // Initial sync to match webclient behavior
        sendRaw({ type: 'init', jwt: jwtRef.current || undefined });
        sendRaw({
          jwt: jwtRef.current || undefined,
          userAction: {
            name: 'modulesList',
            context: {},
          },
        });
        requestClientAuthContext('websocket_open');

        if (heartbeatTimerRef.current != null) {
          clearInterval(heartbeatTimerRef.current);
        }
        heartbeatTimerRef.current = setInterval(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            sendRaw({ type: 'ping' });
          }
        }, 20000) as any;
      };

      ws.onmessage = async (event: MessageEvent) => {
        try {
          const data = await decodeWsMessage(event.data, wsCodec);
          if (Array.isArray(data)) {
            data.forEach((entry) => {
              if (entry && typeof entry === 'object') {
                collectInboundRequestIds(entry).forEach((requestId) => releasePendingAction(requestId));
                runtimeRef.current?.inbound.enqueue(entry);
              }
            });
          } else if (data && typeof data === 'object') {
            collectInboundRequestIds(data).forEach((requestId) => releasePendingAction(requestId));
            runtimeRef.current?.inbound.enqueue(data);
          }
        } catch (err) {
          console.error('[useA2UI] Failed to decode message', err);
        }
      };

      ws.onclose = () => {
        setConnectionState('disconnected');
        wsRef.current = null;
        if (heartbeatTimerRef.current != null) {
          clearInterval(heartbeatTimerRef.current);
          heartbeatTimerRef.current = null;
        }
        if (notificationPollTimerRef.current != null) {
          clearInterval(notificationPollTimerRef.current);
          notificationPollTimerRef.current = null;
        }
        // Simple reconnect logic
        if (!cancelled) {
          reconnectTimerRef.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = (err: Event) => {
        console.error('[useA2UI] WebSocket error', err);
        if (heartbeatTimerRef.current != null) {
          clearInterval(heartbeatTimerRef.current);
          heartbeatTimerRef.current = null;
        }
      };
    };

    // Load persisted JWT before opening the websocket, otherwise the initial
    // init/modulesList requests race without auth and the server renders login.
    AsyncStorage.getItem('democrai_jwt').then(async (token) => {
      if (cancelled) return;
      if (token) {
        persistJwt(token);
        scheduleTokenRefresh(token);
      }
      await loadAuthSession().catch((err) => {
        console.error('[useA2UI] Failed to load auth session', err);
      });
      if (cancelled) return;
      connect();
    }).catch((err) => {
      console.error('[useA2UI] Failed to load persisted JWT', err);
      if (!cancelled) connect();
    });

    return () => {
      cancelled = true;
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (heartbeatTimerRef.current != null) {
        clearInterval(heartbeatTimerRef.current);
      }
      if (notificationPollTimerRef.current != null) {
        clearInterval(notificationPollTimerRef.current);
        notificationPollTimerRef.current = null;
      }
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      clearTokenRefreshTimer();
    };
  }, [
    clearTokenRefreshTimer,
    handleMessageData,
    loadAuthSession,
    persistJwt,
    requestClientAuthContext,
    scheduleTokenRefresh,
    sendRaw,
    wsCodec,
    wsUrl,
  ]);

  useEffect(() => {
    if (connectionState !== 'connected' || !isAuthenticatedRef.current) {
      if (notificationPollTimerRef.current != null) {
        clearInterval(notificationPollTimerRef.current);
        notificationPollTimerRef.current = null;
      }
      return undefined;
    }

    const poll = () => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      if (!isAuthenticatedRef.current) return;
      sendRaw({
        jwt: jwtRef.current || undefined,
        current_path: stateModelRef.current.current_path || stateModelRef.current.global?.current_path || '/',
        userAction: { name: 'get_notifications_count', context: {} },
      });
    };

    poll();
    notificationPollTimerRef.current = setInterval(poll, NOTIFICATION_POLL_INTERVAL_MS);
    return () => {
      if (notificationPollTimerRef.current != null) {
        clearInterval(notificationPollTimerRef.current);
        notificationPollTimerRef.current = null;
      }
    };
  }, [connectionState, sendRaw, userRole]);

  return {
    surfaces,
    dataModel,
    stateModel,
    sendAction,
    closeSurface,
    setInput,
    connectionState,
    jwt,
    userRole,
    userPermissions,
    backgroundTasks,
    pendingActions,
  };
}
