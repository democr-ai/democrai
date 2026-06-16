import { normalizeActive } from './shared';

export interface RuleOptions {
  surfaceModel?: any;
  stateModel?: any;
  item?: Record<string, any>;
  formValues?: Record<string, any>;
  allowImplicitPath?: boolean;
}

export const isObject = (v: any): v is Record<string, any> => typeof v === 'object' && v !== null;

export const getByPath = (obj: any, path: string): any => {
  if (!obj || !path) return obj;
  return path.split(/[./]/).reduce((acc, segment) => {
    if (acc == null || typeof acc !== 'object') return undefined;
    return acc[segment];
  }, obj);
};

const getScopedStateValue = (stateModel: any, scope: string, path: string): any => {
  const normalizedPath = String(path || '').trim().replace(/^\//, '').replace(/\//g, '.');
  if (!normalizedPath) return undefined;

  const scopeKey = String(scope || '').trim().toLowerCase();

  if (scopeKey === 'page') {
    const pageValue = getByPath(stateModel?.page, normalizedPath);
    if (pageValue !== undefined) return pageValue;
    return getByPath(stateModel?.page_state, normalizedPath);
  }

  if (scopeKey === 'global') {
    const fromGlobal = getByPath(stateModel?.global, normalizedPath);
    if (fromGlobal !== undefined) return fromGlobal;
    return getByPath(stateModel, normalizedPath);
  }

  const fromPage = getByPath(stateModel?.page, normalizedPath);
  if (fromPage !== undefined) return fromPage;
  const fromGlobal = getByPath(stateModel?.global, normalizedPath);
  if (fromGlobal !== undefined) return fromGlobal;
  const direct = getByPath(stateModel, normalizedPath);
  if (direct !== undefined) return direct;

  if (scopeKey && stateModel && typeof stateModel === 'object') {
    const scopedObj = stateModel[scopeKey];
    if (scopedObj && typeof scopedObj === 'object') return getByPath(scopedObj, normalizedPath);
  }

  return undefined;
};

const getSurfaceDataValue = (surfaceModel: any, path: string): any => {
  const normalizedPath = String(path || '').trim().replace(/^\//, '').replace(/\//g, '.');
  if (!normalizedPath) return undefined;
  return getByPath(surfaceModel, normalizedPath);
};

export const resolveOperand = (operand: any, options: RuleOptions): any => {
  if (operand === undefined || operand === null) return operand;

  if (isObject(operand)) {
    const type = String(operand.type || '').trim().toLowerCase();
    
    if (type === 'store') {
      const path = String(operand.path || '').trim();
      const scope = String(operand.scope || 'auto').trim();
      const value = getScopedStateValue(options.stateModel, scope, path);
      return value !== undefined ? value : operand.default;
    }

    if (type === 'form') {
      const value = getByPath(options.formValues, String(operand.path || '').trim());
      return value !== undefined ? value : operand.default;
    }

    if (operand.path && Object.keys(operand).every((key) => ['path', 'default'].includes(key))) {
      const value = getSurfaceDataValue(options.surfaceModel, String(operand.path || '').trim());
      return value !== undefined ? value : operand.default;
    }

    if (type === 'data') {
      const value = getSurfaceDataValue(options.surfaceModel, String(operand.path || '').trim());
      return value !== undefined ? value : operand.default;
    }

    if (type === 'literal') {
      return operand.value !== undefined ? operand.value : operand.default;
    }

    if (operand.literalString !== undefined) {
      return operand.literalString;
    }
  }

  if (typeof operand === 'string') {
    if (operand.startsWith('@data/')) {
      return getSurfaceDataValue(options.surfaceModel, operand.slice('@data/'.length));
    }

    if (operand.startsWith('@state/')) {
      const parts = operand.slice('@state/'.length).split('/').filter(Boolean);
      const scope = parts.length > 1 ? String(parts[0]) : 'auto';
      const path = parts.length > 1 ? parts.slice(1).join('/') : parts.join('/');
      return getScopedStateValue(options.stateModel, scope, path);
    }

    if (operand.startsWith('$state.') || operand.startsWith('$global.')) {
      const key = operand.replace(/^\$state\./, '').replace(/^\$global\./, '');
      const scope = operand.startsWith('$global.') ? 'global' : 'page';
      return getScopedStateValue(options.stateModel, scope, key);
    }

    if (operand.startsWith('$item.') && options.item) {
      const key = operand.slice(6);
      return getByPath(options.item, key);
    }

    if (operand.startsWith('$form.')) {
      const key = operand.slice(6);
      return getByPath(options.formValues, key);
    }

    if (operand.startsWith('{{') && operand.endsWith('}}')) {
      const key = operand.slice(2, -2).trim();
      const normalizedKey = key.startsWith('item.') ? key.slice(5) : key;
      const itemVal = getByPath(options.item, normalizedKey);
      if (itemVal !== undefined) return itemVal;
      const formVal = key.startsWith('form.') ? getByPath(options.formValues, key.slice(5)) : undefined;
      if (formVal !== undefined) return formVal;
      return getScopedStateValue(options.stateModel, 'auto', key);
    }
  }

  return operand;
};

export const evaluateCondition = (condition: any, options: RuleOptions): boolean => {
  if (!isObject(condition)) return false;

  const left = resolveOperand(condition.left ?? condition.value1, options);
  const right = resolveOperand(condition.right ?? condition.value2, options);
  const op = String(condition.op ?? condition.operator ?? '==');

  try {
    const res = (() => {
      switch (op) {
        case '==': return left === right;
        case '!=': return left !== right;
        case 'in': return Array.isArray(right) ? right.includes(left) : String(right).includes(String(left));
        case 'contains': return Array.isArray(left) ? left.includes(right) : String(left).includes(String(right));
        case '>': return Number(left) > Number(right);
        case '<': return Number(left) < Number(right);
        case '>=': return Number(left) >= Number(right);
        case '<=': return Number(left) <= Number(right);
        case 'matches': return new RegExp(String(right)).test(String(left));
        case 'exists': return left !== undefined && left !== null;
        case 'empty': return left === undefined || left === null || left === '';
        default: return false;
      }
    })();

    return res;
  } catch {
    return false;
  }
};

export const evaluateRule = (rule: any, options: RuleOptions, defaultVal = false): boolean => {
  if (rule === null || rule === undefined) return defaultVal;
  
  let target = rule;
  if (typeof rule === 'string') {
    if (rule.startsWith('@state/') || rule.startsWith('$state.') || rule.startsWith('$global.') || rule.startsWith('$item.') || rule.startsWith('$form.') || (rule.startsWith('{{') && rule.endsWith('}}'))) {
      target = resolveOperand(rule, options);
    }
  }

  if (typeof target === 'boolean') return target;
  
  if (!isObject(target)) {
    return normalizeActive(target);
  }

  let conditions = (target as any).conditions;
  if (!Array.isArray(conditions)) conditions = [target];

  if (conditions.length === 0) return defaultVal;

  const mode = String((target as any).mode || (target as any).operator || 'AND').toUpperCase();
  const results = conditions.map((c: any) => evaluateCondition(c, options));

  return mode === 'OR' ? results.some(Boolean) : results.every(Boolean);
};

export const resolveActiveValue = (activeProp: any, options: RuleOptions): boolean => {
  return evaluateRule(activeProp, options, false);
};

export const resolveBindings = (data: any, options: RuleOptions): any => {
  if (typeof data === 'string') {
    if (data.startsWith('@data/')) {
      const dataValue = getSurfaceDataValue(options.surfaceModel, data.slice('@data/'.length));
      return dataValue !== undefined ? dataValue : data;
    }

    if (data.startsWith('@state/')) {
      const parts = data.slice('@state/'.length).split('/').filter(Boolean);
      const scope = parts.length > 1 ? String(parts[0]) : '';
      const path = parts.length > 1 ? parts.slice(1).join('/') : parts.join('/');
      const stateValue = getScopedStateValue(options.stateModel, scope, path);
      return stateValue !== undefined ? stateValue : data;
    }

    if (data.startsWith('$state.') || data.startsWith('$global.')) {
      const key = data.replace(/^\$state\./, '').replace(/^\$global\./, '');
      const scope = data.startsWith('$global.') ? 'global' : 'page';
      const val = getScopedStateValue(options.stateModel, scope, key);
      return val !== undefined ? val : data;
    }

    if (data.startsWith('$form.')) {
      const key = data.slice(6);
      const val = getByPath(options.formValues, key);
      return val !== undefined ? val : data;
    }

    if (options.item) {
      if (data.startsWith('$item.')) {
        const key = data.slice(6);
        const val = getByPath(options.item, key);
        return val !== undefined ? val : data;
      }

      const replacedMustache = data.replace(/\{\{\s*([^{}]+?)\s*\}\}/g, (match: string, rawKey: string) => {
        const key = String(rawKey || '').trim();
        const normalizedItemKey = key.startsWith('item.') ? key.slice(5) : key;
        const itemVal = getByPath(options.item, normalizedItemKey);
        if (itemVal !== undefined) return String(itemVal);
        const formVal = key.startsWith('form.') ? getByPath(options.formValues, key.slice(5)) : undefined;
        if (formVal !== undefined) return String(formVal);
        const stateVal = getScopedStateValue(options.stateModel, 'auto', key);
        return stateVal !== undefined ? String(stateVal) : match;
      });
      return replacedMustache.replace(/\$item\.([A-Za-z0-9_.]+)/g, (match: string, rawPath: string) => {
        const itemVal = getByPath(options.item, rawPath);
        return itemVal !== undefined ? String(itemVal) : match;
      });
    }

    if (data.startsWith('{{') && data.endsWith('}}')) {
      const key = data.slice(2, -2).trim();
      const formVal = key.startsWith('form.') ? getByPath(options.formValues, key.slice(5)) : undefined;
      if (formVal !== undefined) return formVal;
      const stateVal = getScopedStateValue(options.stateModel, 'auto', key);
      return stateVal !== undefined ? stateVal : data;
    }

    return data;
  }

  if (Array.isArray(data)) {
    return data.map((entry) => resolveBindings(entry, options));
  }

  if (isObject(data)) {
    if (typeof data.literalString === 'string') {
      return resolveBindings(data.literalString, options);
    }

    const bindingType = String((data as any).type || '').trim().toLowerCase();
    const keys = Object.keys(data as any);
    const isImplicitDataBinding = keys.every((key) => key === 'path' || key === 'default');
    if (options.allowImplicitPath !== false && isImplicitDataBinding && 'path' in (data as any) && !('type' in (data as any))) {
      const dataValue = getSurfaceDataValue(options.surfaceModel, String((data as any).path || '').trim());
      if (dataValue !== undefined) return dataValue;
      if ((data as any).default !== undefined) return resolveBindings((data as any).default, options);
      return '';
    }

    if (bindingType === 'data') {
      const dataValue = getSurfaceDataValue(options.surfaceModel, String((data as any).path || '').trim());
      if (dataValue !== undefined) return dataValue;
      if ((data as any).default !== undefined) return resolveBindings((data as any).default, options);
      return '';
    }

    if (bindingType === 'store') {
      const scope = String((data as any).scope || '').trim().toLowerCase();
      const rawPath = String((data as any).path || '').trim().replace(/^\//, '').replace(/\//g, '.');
      const stateValue = getScopedStateValue(options.stateModel, scope, rawPath);
      if (stateValue !== undefined) return stateValue;
      if ((data as any).default !== undefined) return resolveBindings((data as any).default, options);
      return '';
    }

    if (bindingType === 'form') {
      const formValue = getByPath(options.formValues, String((data as any).path || '').trim());
      if (formValue !== undefined) return formValue;
      if ((data as any).default !== undefined) return resolveBindings((data as any).default, options);
      return '';
    }

    if (bindingType === 'literal') {
      if ((data as any).value !== undefined) return resolveBindings((data as any).value, options);
      if ((data as any).default !== undefined) return resolveBindings((data as any).default, options);
      return '';
    }

    const next: Record<string, any> = {};
    Object.entries(data).forEach(([key, value]) => {
      if (key === 'children') {
        next[key] = value;
      } else {
        next[key] = resolveBindings(value, options);
      }
    });
    return next;
  }

  return data;
};

export { normalizeActive };
