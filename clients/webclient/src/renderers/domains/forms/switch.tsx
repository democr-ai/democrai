import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm, toBoolean } from '@/renderers/shared';
import { Switch as UISwitch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

export const Switch: React.FC<any> = ({ id, label, checked, action, onAction, setInput, style, error }) => {
  const [local, setLocal] = React.useState(toBoolean(checked));

  React.useEffect(() => {
    setLocal(toBoolean(checked));
  }, [checked]);

  const onChange = async (next: boolean) => {
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
    <div className="grid gap-1.5" style={parseStyle(style)}>
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id} className={cn(error && "text-destructive")}>{getLiteral(label)}</Label>
        <UISwitch id={id} checked={local} onCheckedChange={onChange} className={cn(error && "data-[state=unchecked]:border-destructive/50")} />
      </div>
      {error && (
        <p className="text-[12px] font-medium text-destructive mt-0.5 animate-in fade-in slide-in-from-top-1 duration-200">
          {error}
        </p>
      )}
    </div>
  );
};
