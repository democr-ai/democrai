import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';
import { ChoiceGroup, type IChoiceGroupOption } from '@fluentui/react';

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

  const handleChange = async (_e?: React.FormEvent<HTMLElement | HTMLInputElement>, option?: IChoiceGroupOption) => {
    const next = String(option?.key || '');
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
  const choiceOptions: IChoiceGroupOption[] = normalized.map((option) => ({
    key: String(option.value),
    text: String(option.label),
  }));

  return (
    <div
      className="a2ui-field a2ui-radio-group"
      style={parseStyle(style)}
    >
      <ChoiceGroup
        className="a2ui-radio-options"
        label={labelText || undefined}
        selectedKey={selected}
        options={choiceOptions}
        onChange={(event, option) => { void handleChange(event, option); }}
      />
      {error && <div className="text-danger small mt-1">{error}</div>}
    </div>
  );
};
