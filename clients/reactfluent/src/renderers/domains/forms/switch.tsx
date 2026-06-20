import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm, toBoolean } from '@/renderers/shared';
import { Toggle } from '@fluentui/react';

export const Switch: React.FC<any> = ({ id, label, checked, action, onAction, setInput, style, error }) => {
  const [local, setLocal] = React.useState(toBoolean(checked));

  React.useEffect(() => {
    setLocal(toBoolean(checked));
  }, [checked]);

  const onChange = async (_e?: React.MouseEvent<HTMLElement>, checked?: boolean) => {
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
    <div
      className="ds-field m-0"
      style={parseStyle(style)}
    >
      <Toggle
        id={id}
        className="ds-toggle"
        label={getLiteral(label)}
        checked={local}
        onChange={(event, checked) => { void onChange(event, checked); }}
      />
      {error && <div className="text-danger small mt-1">{error}</div>}
    </div>
  );
};
