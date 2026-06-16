import { readClientStateValue } from '@/state/clientState';

type TransformContext = {
  stateModel?: any;
  row?: Record<string, any>;
};

type FormatterFn = (value: any, args?: string[], ctx?: TransformContext) => string;

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

const registry: Record<string, FormatterFn> = {};

function register(name: string, fn: FormatterFn): void {
  registry[name] = fn;
}

// ---------------------------------------------------------------------------
// Built-in formatters
// ---------------------------------------------------------------------------

function formatDateString(value: any, fmt = '%Y-%m-%d'): string {
  try {
    const text = String(value ?? '');
    const d = new Date(text);
    if (isNaN(d.getTime())) return text;
    return fmt
      .replace('%Y', String(d.getFullYear()))
      .replace('%m', String(d.getMonth() + 1).padStart(2, '0'))
      .replace('%d', String(d.getDate()).padStart(2, '0'))
      .replace('%H', String(d.getHours()).padStart(2, '0'))
      .replace('%M', String(d.getMinutes()).padStart(2, '0'))
      .replace('%S', String(d.getSeconds()).padStart(2, '0'));
  } catch {
    return String(value ?? '');
  }
}

function getStubRecord(stateModel: any, stubName: string, keyValue: any): Record<string, any> | null {
  if (!stateModel || !stubName) return null;
  const rows = readClientStateValue(stateModel, 'auto', `/stubs/${stubName}`);
  if (!Array.isArray(rows)) return null;
  const keyText = String(keyValue);
  for (const row of rows) {
    if (!row || typeof row !== 'object') continue;
    const candidate = (row as any).key;
    if (candidate === keyValue || String(candidate) === keyText) return row as Record<string, any>;
  }
  return null;
}

register('upper', (value) => String(value ?? '').toUpperCase());

register('lower', (value) => String(value ?? '').toLowerCase());

register('title', (value) =>
  String(value ?? '').replace(/\b\w/g, (c) => c.toUpperCase()),
);

register('truncate', (value, args = []) => {
  const n = args[0] ?? '50';
  const text = String(value ?? '');
  const limit = parseInt(n, 10);
  return isNaN(limit) ? text : text.length > limit ? text.slice(0, limit) + '…' : text;
});

register('date', (value, args = []) => {
  const fmt = args[0] ?? '%Y-%m-%d';
  return formatDateString(value, fmt);
});

register('join_list', (value, args = [], ctx = {}) => {
  /**
   * Join a list of primitive values.
   * transform: "join_list|<sep>|<inner_transform>"
   * Example:   "join_list|, |upper"  →  "READ, WRITE, ADMIN"
   */
  const sep = args[0] ?? ', ';
  const inner = args[1] ?? '';
  if (!Array.isArray(value)) return applyTransform(value, undefined, ctx);
  return value.map((v) => (inner ? applyTransform(v, inner, ctx) : String(v ?? ''))).join(sep);
});

register('join_objects', (value, args = [], ctx = {}) => {
  /**
   * Join a list of objects extracting a specific key from each.
   * transform: "join_objects|<key>|<sep>|<inner_transform>"
   * Example:   "join_objects|name|, |title"  →  "Backend, Platform"
   */
  const key = args[0] ?? '';
  const sep = args[1] ?? ', ';
  const inner = args[2] ?? '';
  if (!Array.isArray(value)) return applyTransform(value, undefined, ctx);
  return value
    .map((obj) => {
      const v = obj && typeof obj === 'object' ? (obj[key] ?? '') : obj;
      return inner ? applyTransform(v, inner, ctx) : String(v ?? '');
    })
    .join(sep);
});

register('get_stub', (value, args = [], ctx = {}) => {
  const stubName = String(args[0] ?? '').trim();
  const outputField = String(args[1] ?? 'value').trim() || 'value';
  const stateModel = ctx?.stateModel;
  const record = getStubRecord(stateModel, stubName, value);
  if (!record) return String(value ?? '');
  const resolved = record[outputField] ?? (outputField !== 'value' ? record.value : undefined);
  return resolved == null ? String(value ?? '') : String(resolved);
});

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Format *value* according to *transform*.
 *
 * New syntax  — pipe-separated:  "func_name|arg1|arg2|..."
 * Legacy syntax — colon-separated (backward compat): "date:%Y-%m-%d", "truncate:20"
 */
export function applyTransform(
  value: any,
  transform: string | undefined,
  ctx: TransformContext = {},
): string {
  if (value === null || value === undefined) return '';
  if (!transform) return String(value);

  // New pipe-separated syntax
  if (transform.includes('|')) {
    const [funcName, ...args] = transform.split('|');
    try {
      const fn = registry[funcName.trim()];
      if (!fn) return String(value);
      return fn(value, args, ctx);
    } catch {
      return String(value);
    }
  }

  // Legacy colon syntax — kept for backward compatibility
  if (transform === 'upper') return String(value).toUpperCase();
  if (transform === 'lower') return String(value).toLowerCase();
  if (transform === 'title') return String(value).replace(/\b\w/g, (c) => c.toUpperCase());
  if (transform.startsWith('truncate:')) {
    const n = parseInt(transform.split(':')[1], 10);
    const text = String(value);
    return isNaN(n) ? text : text.length > n ? text.slice(0, n) + '…' : text;
  }
  if (transform.startsWith('date:')) {
    const fmt = transform.slice(5);
    return formatDateString(value, fmt);
  }
  if (transform.startsWith('get_stub:')) {
    const parts = transform.split(':');
    const stubName = parts[1] ?? '';
    const outputField = parts[2] ?? 'value';
    const getStub = registry['get_stub'];
    if (getStub) return getStub(value, [stubName, outputField], ctx);
    return String(value);
  }

  // Fallback: try registry with no args
  try {
    const fn = registry[transform];
    if (fn) return fn(value, [], ctx);
  } catch {
    // ignore
  }

  return String(value);
}
