import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';
import {
  Select as UISelect,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

const arraysEqual = (a: string[], b: string[]): boolean => {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
};

const EMPTY_SELECT_ITEM_VALUE = '__democrai_empty_select_value__';

export const Select: React.FC<any> = ({
  id,
  label,
  options = [],
  value,
  placeholder,
  multiple,
  action,
  onAction,
  setInput,
  style,
  error,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const isMultiple = Boolean(multiple);
  const hasEmptySingleOption = React.useMemo(
    () => !isMultiple && normalized.some((option) => String(option.value) === ''),
    [isMultiple, normalized],
  );

  const normalizedMultiValue = React.useMemo(() => {
    if (!isMultiple) return [] as string[];
    if (Array.isArray(value)) return value.map((item) => String(item));
    if (value == null || value === '') return [] as string[];
    return [String(value)];
  }, [isMultiple, value]);

  const [localValue, setLocalValue] = React.useState(value == null ? '' : String(value));
  const [localValues, setLocalValues] = React.useState<string[]>(normalizedMultiValue);
  const lastExternalSingleRef = React.useRef<string>(value == null ? '' : String(value));
  const lastExternalMultiRef = React.useRef<string>(normalizedMultiValue.join('\u0001'));

  React.useEffect(() => {
    if (isMultiple) {
      const externalKey = normalizedMultiValue.join('\u0001');
      const externalChanged = externalKey !== lastExternalMultiRef.current;
      if (externalChanged) {
        lastExternalMultiRef.current = externalKey;
        setLocalValues((prev) => (arraysEqual(prev, normalizedMultiValue) ? prev : normalizedMultiValue));
      }
      return;
    }
    const next = value == null ? '' : String(value);
    const externalChanged = next !== lastExternalSingleRef.current;
    if (externalChanged) {
      lastExternalSingleRef.current = next;
      setLocalValue((prev) => (prev === next ? prev : next));
    }
  }, [isMultiple, normalizedMultiValue, value]);

  const commitSingle = async (next: string) => {
    const nextValue = next === EMPTY_SELECT_ITEM_VALUE ? '' : next;
    if (localValue === nextValue) return;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      return;
    }
    setLocalValue(nextValue);
    setInput?.(id, nextValue);
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: nextValue, value: nextValue });
  };

  const commitMultiple = async (next: string[]) => {
    if (!arraysEqual(localValues, next)) {
      if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
        return;
      }
      setLocalValues(next);
      setInput?.(id, next);
      const actionWithoutConfirm = action && typeof action === 'object'
        ? { ...action, confirm: undefined }
        : action;
      emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
    }
  };

  const toggleMultipleValue = (rawValue: string) => {
    const target = String(rawValue);
    const order = new Map(normalized.map((entry, index) => [String(entry.value), index]));
    const nextSet = new Set(localValues);
    if (nextSet.has(target)) {
      nextSet.delete(target);
    } else {
      nextSet.add(target);
    }
    const next = Array.from(nextSet).sort((left, right) => {
      const leftPos = order.get(left) ?? Number.MAX_SAFE_INTEGER;
      const rightPos = order.get(right) ?? Number.MAX_SAFE_INTEGER;
      return leftPos - rightPos;
    });
    commitMultiple(next);
  };

  if (isMultiple) {
    return (
      <div className="grid gap-1.5" style={parseStyle(style)}>
        {label ? (
          <Label className={cn(error && 'text-destructive')}>
            {getLiteral(label)}
          </Label>
        ) : null}

        <div
          className={cn(
            'min-h-28 rounded-md border border-input bg-background p-1.5 text-sm shadow-xs',
            error && 'border-destructive/50 bg-destructive/5',
          )}
        >
          <div className="grid gap-1">
            {normalized.map((option, index) => {
              const optionValue = String(option.value);
              const selected = localValues.includes(optionValue);
              return (
                <button
                  key={`${id}_multi_opt_${index}`}
                  type="button"
                  onClick={() => toggleMultipleValue(optionValue)}
                  className={cn(
                    'flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-left transition-colors',
                    selected
                      ? 'bg-primary/15 text-foreground'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  <span>{option.label}</span>
                  {selected ? <i className="ri-check-line text-sm text-primary" /> : null}
                </button>
              );
            })}
          </div>
        </div>

        {error && (
          <p className="text-[12px] font-medium text-destructive mt-0.5 animate-in fade-in slide-in-from-top-1 duration-200">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="grid gap-1.5" style={parseStyle(style)}>
      {label ? (
        <Label className={cn(error && 'text-destructive')}>
          {getLiteral(label)}
        </Label>
      ) : null}
      <UISelect
        value={hasEmptySingleOption && localValue === '' ? EMPTY_SELECT_ITEM_VALUE : localValue}
        onValueChange={commitSingle}
      >
        <SelectTrigger className={cn(error && 'border-destructive/50 focus:ring-destructive/50 bg-destructive/5')}>
          <SelectValue placeholder={getLiteral(placeholder || 'Select an option')} />
        </SelectTrigger>
        <SelectContent>
          {normalized.map((option, index) => (
            <SelectItem
              key={`${id}_opt_${index}`}
              value={String(option.value) === '' ? EMPTY_SELECT_ITEM_VALUE : String(option.value)}
            >
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </UISelect>
      {error && (
        <p className="text-[12px] font-medium text-destructive mt-0.5 animate-in fade-in slide-in-from-top-1 duration-200">
          {error}
        </p>
      )}
    </div>
  );
};
