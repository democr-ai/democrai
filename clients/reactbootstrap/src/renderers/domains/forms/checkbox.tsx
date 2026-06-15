import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm, toBoolean } from '@/renderers/shared';
import { FormGroup, Label, Input } from 'design-react-kit';

export const Checkbox: React.FC<any> = ({ id, label, checked, action, onAction, setInput, style, error, syncInitialInput = true }) => {
  const [local, setLocal] = React.useState(toBoolean(checked));

  React.useEffect(() => {
    const next = toBoolean(checked);
    setLocal(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [checked, id, setInput, syncInitialInput]);

  const onChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.checked;
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
    <FormGroup check style={parseStyle(style)}>
      <Input
        id={id}
        type="checkbox"
        checked={local}
        onChange={onChange}
        valid={error ? false : undefined}
      />
      <Label for={id} check className={error ? "text-danger" : ""}>
        {getLiteral(label)}
      </Label>
      {error && <div className="text-danger small mt-1">{error}</div>}
    </FormGroup>
  );
};
