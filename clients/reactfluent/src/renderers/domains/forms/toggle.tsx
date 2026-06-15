import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm } from '@/renderers/shared';
import { Toggle as FluentToggle } from '@fluentui/react';

export const Toggle: React.FC<any> = ({
  id,
  label,
  checked,
  action,
  onAction,
  setInput,
  style,
  error,
  syncInitialInput = true,
}) => {
  const [value, setValue] = React.useState(Boolean(checked));

  React.useEffect(() => {
    const next = Boolean(checked);
    setValue(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [checked, id, setInput, syncInitialInput]);

  const handleChange = async (isChecked: boolean) => {
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      return;
    }
    setValue(isChecked);
    setInput?.(id, isChecked);
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, {
      [id]: isChecked,
      checked: isChecked,
      value: isChecked,
    });
  };

  return (
    <div
      style={parseStyle(style)}
      className="a2ui-field m-0"
    >
      <FluentToggle
        id={id}
        label={getLiteral(label)}
        checked={value}
        onChange={(_event, checked) => { void handleChange(Boolean(checked)); }}
      />
      {error && <div className="text-danger small mt-1">{error}</div>}
    </div>
  );
};
