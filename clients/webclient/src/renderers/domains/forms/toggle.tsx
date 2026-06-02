import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm } from '@/renderers/shared';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';

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
    <div className="grid gap-1.5" style={parseStyle(style)}>
      <div className="flex items-center gap-3">
        <Switch
          id={id}
          checked={value}
          onCheckedChange={handleChange}
          className={cn(error && 'data-[state=unchecked]:border-destructive/50')}
        />
        <Label htmlFor={id} className={cn(error && 'text-destructive')}>
          {getLiteral(label)}
        </Label>
      </div>
      {error && (
        <p className="text-[12px] font-medium text-destructive mt-0.5 animate-in fade-in slide-in-from-top-1 duration-200">
          {error}
        </p>
      )}
    </div>
  );
};
