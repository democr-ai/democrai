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

const materializeActionContext = (
  ctx: Record<string, any>,
  extra: Record<string, any>,
): Record<string, any> => {
  const itemSource = (
    extra && typeof extra.item === 'object' && extra.item !== null
      ? extra.item
      : extra
  );

  const resolve = (value: any): any => {
    if (typeof value === 'string') {
      if (value === '$item') {
        return itemSource;
      }
      if (value.startsWith('$item.')) {
        return resolveByPath(itemSource, value.slice(6));
      }

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

    if (Array.isArray(value)) {
      return value.map(resolve);
    }

    if (value && typeof value === 'object') {
      const next: Record<string, any> = {};
      Object.entries(value).forEach(([key, nested]) => {
        next[key] = resolve(nested);
      });
      return next;
    }

    return value;
  };

  return resolve(ctx || {});
};

export const emitActionSpec = (
  action: any,
  onAction: ((name: string, ctx: any) => void) | undefined,
  extra: Record<string, any> = {},
) => {
  const { name, context, confirm } = parseActionSpec(action);
  if (!name || !onAction) {
    return;
  }
  const payload = { ...materializeActionContext(context, extra), ...extra };
  const dispatch = () => {
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

export const requestActionConfirm = (confirm: any): Promise<boolean> => {
  const text = getLiteral(confirm?.text, 'Are you sure?');
  const confirmText = getLiteral(confirm?.confirm_text, 'Confirm');
  const cancelText = getLiteral(confirm?.cancel_text, 'Cancel');

  if (typeof document === 'undefined') {
    return Promise.resolve(typeof window !== 'undefined' ? window.confirm(text) : false);
  }

  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.setAttribute('role', 'presentation');
    overlay.style.position = 'fixed';
    overlay.style.inset = '0';
    overlay.style.zIndex = '9999';
    overlay.style.display = 'flex';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';
    overlay.style.background = 'rgba(15, 23, 42, 0.42)';

    const dialog = document.createElement('div');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.style.width = 'min(420px, calc(100vw - 32px))';
    dialog.style.borderRadius = '12px';
    dialog.style.background = 'var(--background, #fff)';
    dialog.style.color = 'var(--foreground, #0f172a)';
    dialog.style.boxShadow = '0 18px 50px rgba(15, 23, 42, 0.22)';
    dialog.style.padding = '18px';

    const message = document.createElement('p');
    message.textContent = text;
    message.style.margin = '0 0 18px';
    message.style.fontSize = '14px';
    message.style.lineHeight = '1.45';

    const actions = document.createElement('div');
    actions.style.display = 'flex';
    actions.style.justifyContent = 'flex-end';
    actions.style.gap = '8px';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = cancelText;
    cancel.style.height = '32px';
    cancel.style.border = '1px solid var(--border, #d4d4d8)';
    cancel.style.borderRadius = '8px';
    cancel.style.padding = '0 12px';
    cancel.style.background = 'transparent';
    cancel.style.color = 'inherit';

    const accept = document.createElement('button');
    accept.type = 'button';
    accept.textContent = confirmText;
    accept.style.height = '32px';
    accept.style.border = '1px solid transparent';
    accept.style.borderRadius = '8px';
    accept.style.padding = '0 12px';
    accept.style.background = 'var(--primary, #18181b)';
    accept.style.color = 'var(--primary-foreground, #fff)';

    function finish(accepted: boolean) {
      document.removeEventListener('keydown', onKeyDown);
      overlay.remove();
      resolve(accepted);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') finish(false);
    }

    cancel.addEventListener('click', () => finish(false));
    accept.addEventListener('click', () => finish(true));
    document.addEventListener('keydown', onKeyDown);

    actions.append(cancel, accept);
    dialog.append(message, actions);
    overlay.append(dialog);
    document.body.append(overlay);
    accept.focus();
  });
};

export const normalizeTrackedActionNames = (trackLoading: any, fallbackActionName = ''): string[] => {
  const names = Array.isArray(trackLoading)
    ? trackLoading
    : trackLoading ? [trackLoading] : [];
  const normalized = names
    .map((entry: any) => String(entry || '').trim())
    .filter(Boolean);
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
