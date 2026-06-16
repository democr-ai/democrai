import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm, toBoolean } from '@/renderers/shared';
import { Checkbox as FluentCheckbox } from '@fluentui/react';

export const Checkbox: React.FC<any> = ({ id, label, checked, action, onAction, setInput, style, error, syncInitialInput = true }) => {
  const [local, setLocal] = React.useState(toBoolean(checked));

  React.useEffect(() => {
    const next = toBoolean(checked);
    setLocal(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [checked, id, setInput, syncInitialInput]);

  const onChange = async (_e?: React.FormEvent<HTMLElement | HTMLInputElement>, checked?: boolean) => {
    const next = Boolean(checked);
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      return;
    }
    setLocal(next);
    setInput?.(id, next);
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, checked: next, value: next });
  };

  return (
    <div className="ds-checkbox-field" style={parseStyle(style)}>
      <FluentCheckbox
        id={id}
        checked={local}
        onChange={onChange}
        label={getLiteral(label)}
      />
      {error && <div className="text-danger small mt-1">{error}</div>}
    </div>
  );
};
