import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';
import { Dropdown, type IDropdownOption } from '@fluentui/react';

const arraysEqual = (a: string[], b: string[]): boolean => {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
};

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
  syncInitialInput = true,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const isMultiple = Boolean(multiple);

  const normalizedMultiValue = React.useMemo(() => {
    if (!isMultiple) return [] as string[];
    if (Array.isArray(value)) return value.map((item) => String(item));
    if (value == null || value === '') return [] as string[];
    return [String(value)];
  }, [isMultiple, value]);
  const normalizedMultiSignature = normalizedMultiValue.join('\u0001');

  const [localValue, setLocalValue] = React.useState(value == null ? '' : String(value));
  const [localValues, setLocalValues] = React.useState<string[]>(normalizedMultiValue);

  React.useEffect(() => {
    if (!isMultiple) return;
    setLocalValues((prev) => (arraysEqual(prev, normalizedMultiValue) ? prev : normalizedMultiValue));
    if (syncInitialInput) setInput?.(id, normalizedMultiValue);
  }, [id, isMultiple, normalizedMultiSignature, setInput, syncInitialInput]);

  React.useEffect(() => {
    if (isMultiple) return;
    const next = value == null ? '' : String(value);
    setLocalValue((prev) => (prev === next ? prev : next));
    if (syncInitialInput) setInput?.(id, next);
  }, [id, isMultiple, setInput, syncInitialInput, value]);

  const emitValue = (next: string | string[]) => {
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
  };

  const commitMultiValue = async (next: string[]) => {
    if (arraysEqual(localValues, next)) return;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      return;
    }
    setLocalValues(next);
    setInput?.(id, next);
    emitValue(next);
  };

  const handleMultiToggle = async (optionValue: string) => {
    const next = localValues.includes(optionValue)
      ? localValues.filter((item) => item !== optionValue)
      : [...localValues, optionValue];
    await commitMultiValue(next);
  };

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = e.target.value;
    if (localValue === next) return;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      return;
    }
    setLocalValue(next);
    setInput?.(id, next);
    emitValue(next);
  };

  const labelText = getLiteral(label);
  const selectedLabels = normalized
    .filter((option) => localValues.includes(String(option.value)))
    .map((option) => option.label);
  const dropdownOptions: IDropdownOption[] = normalized.map((option) => ({
    key: String(option.value),
    text: String(option.label),
  }));

  return (
    <div
      className="ds-field"
      style={parseStyle(style)}
    >
      {isMultiple ? (
        <>
          <Dropdown
            id={id}
            label={labelText || undefined}
            placeholder={getLiteral(placeholder || 'Select options')}
            multiSelect
            selectedKeys={localValues}
            options={dropdownOptions}
            errorMessage={error || undefined}
            className="ds-select ds-select-multiple"
            onChange={(_, option) => {
              if (!option) return;
              void handleMultiToggle(String(option.key));
            }}
          />
          <div className="ds-multi-select-summary" aria-live="polite">
            {selectedLabels.length > 0 ? (
              <>
                <span className="ds-multi-select-count">{selectedLabels.length} selected</span>
                {selectedLabels.map((selectedLabel) => (
                  <span key={String(selectedLabel)} className="ds-multi-select-chip">{selectedLabel}</span>
                ))}
              </>
            ) : (
              <span className="text-muted">No selection</span>
            )}
          </div>
        </>
      ) : (
        <Dropdown
          id={id}
          label={labelText || undefined}
          className="ds-select ds-select-single"
          selectedKey={localValue || undefined}
          placeholder={getLiteral(placeholder || 'Select an option')}
          options={dropdownOptions}
          errorMessage={error || undefined}
          onChange={(_, option) => {
            const next = String(option?.key ?? '');
            void handleChange({ target: { value: next } } as React.ChangeEvent<HTMLSelectElement>);
          }}
        />
      )}
    </div>
  );
};
