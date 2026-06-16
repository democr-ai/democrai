import { Alert } from 'react-native';

export const getLiteral = (value: any, fallback = ''): string => {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && typeof value.literalString === 'string') {
    return value.literalString;
  }
  return value == null ? fallback : String(value);
};

export const toBoolean = (value: any): boolean => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    return ['true', '1', 'yes', 'on'].includes(normalized);
  }
  return Boolean(value);
};

export const parseActionSpec = (action: any): { name: string; context: Record<string, any>; confirm?: any } => {
  if (typeof action === 'string') {
    return { name: action, context: {} };
  }
  if (action && typeof action === 'object' && typeof action.name === 'string') {
    return {
      name: action.name,
      context: action.context && typeof action.context === 'object' ? action.context : {},
      confirm: action.confirm,
    };
  }
  return { name: '', context: {} };
};

const resolveByPath = (obj: any, path: string): any => {
  if (obj == null || !path) return obj;
  return String(path).split('.').reduce((acc, segment) => (
    acc == null || typeof acc !== 'object' ? undefined : acc[segment]
  ), obj);
};

export const materializeActionContext = (
  ctx: Record<string, any>,
  extra: Record<string, any>,
): Record<string, any> => {
  const itemSource = extra && typeof extra.item === 'object' && extra.item !== null ? extra.item : extra;

  const resolve = (value: any): any => {
    if (typeof value === 'string') {
      if (value === '$item') return itemSource;
      if (value.startsWith('$item.')) return resolveByPath(itemSource, value.slice(6));

      const withMustache = value.replace(/\{\{\s*(.*?)\s*\}\}/g, (_m, p1) => {
        const rawKey = String(p1 || '').trim();
        const normalizedKey = rawKey.replace(/^item\./, '');
        const val = resolveByPath(itemSource, normalizedKey);
        return val == null ? '' : String(val);
      });

      return withMustache.replace(/\$item\.([A-Za-z0-9_.]+)/g, (_m, rawPath) => {
        const val = resolveByPath(itemSource, String(rawPath || '').trim());
        return val == null ? '' : String(val);
      });
    }
    if (Array.isArray(value)) return value.map(resolve);
    if (value && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).map(([key, nested]) => [key, resolve(nested)]));
    }
    return value;
  };

  return resolve(ctx || {});
};

export const requestActionConfirm = (confirm: any): Promise<boolean> => {
  const text = getLiteral(confirm?.text, 'Are you sure?');
  const confirmText = getLiteral(confirm?.confirm_text, 'Confirm');
  const cancelText = getLiteral(confirm?.cancel_text, 'Cancel');

  return new Promise((resolve) => {
    Alert.alert('', text, [
      { text: cancelText, style: 'cancel', onPress: () => resolve(false) },
      { text: confirmText, style: 'default', onPress: () => resolve(true) },
    ]);
  });
};

export const emitActionSpec = (
  action: any,
  onAction: ((name: string, ctx: any) => void) | undefined,
  extra: Record<string, any> = {},
) => {
  const { name, context, confirm } = parseActionSpec(action);
  if (!name || !onAction) {
    console.log('[reactnative:action:emit:skip]', { action, hasOnAction: Boolean(onAction) });
    return;
  }
  const payload = { ...materializeActionContext(context, extra), ...extra };
  const dispatch = () => {
    console.log('[reactnative:action:emit]', { name, payload });
    onAction(name, payload);
  };
  if (confirm && typeof confirm === 'object') {
    requestActionConfirm(confirm).then((accepted) => {
      if (accepted) dispatch();
    });
    return;
  }
  dispatch();
};

export const normalizeTrackedActionNames = (trackLoading: any, fallbackActionName = ''): string[] => {
  const names = Array.isArray(trackLoading) ? trackLoading : trackLoading ? [trackLoading] : [];
  const normalized = names.map((entry: any) => String(entry || '').trim()).filter(Boolean);
  if (normalized.length > 0) return normalized;
  const fallback = String(fallbackActionName || '').trim();
  return fallback ? [fallback] : [];
};

export const isAnyTrackedActionPending = (
  pendingActions: Record<string, number> | undefined,
  trackLoading: any,
  fallbackActionName = '',
): boolean => (
  normalizeTrackedActionNames(trackLoading, fallbackActionName)
    .some((name) => (pendingActions?.[name] ?? 0) > 0)
);

export const normalizeOptions = (options: any): Array<{ label: string; value: any }> => {
  if (!Array.isArray(options)) return [];
  return options.map((option) => {
    if (option && typeof option === 'object') {
      return {
        label: getLiteral(option.label || option.value || ''),
        value: option.value,
      };
    }
    return {
      label: getLiteral(option),
      value: option,
    };
  });
};

export const normalizeActive = (value: any): boolean => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    return ['true', '1', 'yes', 'on'].includes(normalized);
  }
  return Boolean(value);
};
