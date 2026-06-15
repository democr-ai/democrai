import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';
import { FormGroup, Label, Input } from 'design-react-kit';

export const RadioGroup: React.FC<any> = ({
  id,
  label,
  options = [],
  value,
  action,
  onAction,
  setInput,
  style,
  error,
  syncInitialInput = true,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const [selected, setSelected] = React.useState(value == null ? '' : String(value));

  React.useEffect(() => {
    const next = value == null ? '' : String(value);
    setSelected(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      return;
    }
    setSelected(next);
    setInput?.(id, next);
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
  };

  const labelText = getLiteral(label);

  return (
    <div className="a2ui-field a2ui-radio-group" style={parseStyle(style)}>
      {labelText && <Label className={`a2ui-radio-group-label ${error ? 'text-danger' : ''}`}>{labelText}</Label>}
      <div className="a2ui-radio-options">
        {normalized.map((option, index) => {
          const optionValue = String(option.value);
          const optionLabel = option.label;
          const radioId = `${id}_radio_${index}`;
          return (
            <FormGroup key={radioId} check className="a2ui-radio-option">
              <Input
                id={radioId}
                name={id}
                type="radio"
                value={optionValue}
                checked={selected === optionValue}
                onChange={handleChange}
                valid={error ? false : undefined}
              />
              <Label for={radioId} check className={error ? "text-danger" : ""}>
                {optionLabel}
              </Label>
            </FormGroup>
          );
        })}
      </div>
      {error && <div className="text-danger small mt-1">{error}</div>}
    </div>
  );
};
