import { emitActionSpec } from '@/renderers/shared';

type ActionSpec = {
  name: string;
  context: Record<string, any>;
  confirm?: any;
};

type Listener = {
  taskId: string;
  actions: Partial<Record<string, ActionSpec>>;
  onAction: (name: string, ctx: any) => void;
};

const listeners = new Map<string, Listener>();

const normalizeActionSpec = (spec: any): ActionSpec | null => {
  if (typeof spec === 'string' && spec.trim()) {
    return { name: spec.trim(), context: {} };
  }
  if (spec && typeof spec === 'object' && typeof spec.name === 'string' && spec.name.trim()) {
    return {
      name: spec.name.trim(),
      context: spec.context && typeof spec.context === 'object' ? spec.context : {},
      confirm: spec.confirm,
    };
  }
  return null;
};

export const registerBackgroundTaskListener = (
  listenerId: string,
  {
    taskId,
    actions,
    onAction,
  }: {
    taskId: string;
    actions: Record<string, any>;
    onAction: (name: string, ctx: any) => void;
  },
) => {
  const normalized: Partial<Record<string, ActionSpec>> = {};
  Object.entries(actions || {}).forEach(([key, value]) => {
    const spec = normalizeActionSpec(value);
    if (spec) {
      normalized[key] = spec;
    }
  });
  if (Object.keys(normalized).length === 0) {
    listeners.delete(listenerId);
    return;
  }
  listeners.set(listenerId, {
    taskId: String(taskId || '').trim(),
    actions: normalized,
    onAction,
  });
};

export const unregisterBackgroundTaskListener = (listenerId: string) => {
  listeners.delete(listenerId);
};

export const dispatchBackgroundTaskEvent = (
  actionKey: string,
  eventName: string,
  payload: Record<string, any>,
) => {
  const taskId = String(payload?.taskId ?? payload?.task_id ?? '').trim();
  listeners.forEach((listener) => {
    const action = listener.actions[actionKey];
    if (!action) {
      return;
    }
    if (taskId && listener.taskId && listener.taskId !== taskId) {
      return;
    }
    emitActionSpec(action, listener.onAction, {
      ...payload,
      event_name: eventName,
      ...(taskId ? { task_id: taskId } : {}),
    });
  });
};
