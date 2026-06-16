import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';
import { FormGroup, Label, Input, FormFeedback } from 'design-react-kit';

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

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
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

  return (
    <FormGroup className="a2ui-field" style={parseStyle(style)}>
      {labelText && <Label for={id}>{labelText}</Label>}
      {isMultiple ? (
        <>
          <div
            id={id}
            role="listbox"
            aria-multiselectable="true"
            aria-invalid={error ? true : undefined}
            className={`a2ui-multi-select ${error ? 'is-invalid' : ''}`}
          >
            {normalized.map((option, index) => {
              const optionValue = String(option.value);
              const selected = localValues.includes(optionValue);
              return (
                <label
                  key={`${id}_opt_${index}`}
                  role="option"
                  aria-selected={selected}
                  className={`a2ui-multi-select-option ${selected ? 'is-selected' : ''}`}
                  htmlFor={`${id}_${index}`}
                >
                  <input
                    id={`${id}_${index}`}
                    type="checkbox"
                    className="a2ui-multi-select-input"
                    checked={selected}
                    onChange={() => handleMultiToggle(optionValue)}
                  />
                  <span className="a2ui-multi-select-check" aria-hidden="true">
                    {selected && <i className="ri-check-line" />}
                  </span>
                  <span className="a2ui-multi-select-label">{option.label}</span>
                </label>
              );
            })}
          </div>
          <div className="a2ui-multi-select-summary" aria-live="polite">
            {selectedLabels.length > 0 ? (
              <>
                <span className="a2ui-multi-select-count">{selectedLabels.length} selected</span>
                {selectedLabels.map((selectedLabel) => (
                  <span key={String(selectedLabel)} className="a2ui-multi-select-chip">{selectedLabel}</span>
                ))}
              </>
            ) : (
              <span className="text-muted">No selection</span>
            )}
          </div>
        </>
      ) : (
        <Input
          id={id}
          type="select"
          tag="select"
          className="a2ui-select a2ui-select-single"
          value={localValue}
          onChange={handleChange}
          valid={error ? false : undefined}
        >
          <option value="" disabled>{getLiteral(placeholder || 'Select an option')}</option>
          {normalized.map((option, index) => (
            <option key={`${id}_opt_${index}`} value={String(option.value)}>
              {option.label}
            </option>
          ))}
        </Input>
      )}
      {error && <FormFeedback>{error}</FormFeedback>}
    </FormGroup>
  );
};
