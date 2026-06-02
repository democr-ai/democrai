import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm, toBoolean } from '@/renderers/shared';
import { Checkbox as UICheckbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

export const Checkbox: React.FC<any> = ({ id, label, checked, action, onAction, setInput, style, error, syncInitialInput = true }) => {
  const [local, setLocal] = React.useState(toBoolean(checked));

  React.useEffect(() => {
    const next = toBoolean(checked);
    setLocal(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [checked, id, setInput, syncInitialInput]);

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
      <div className="flex items-center gap-2.5">
        <UICheckbox id={id} checked={local} onCheckedChange={(next) => onChange(Boolean(next))} className={cn(error && "border-destructive/50 data-[state=checked]:bg-destructive data-[state=checked]:border-destructive")} />
        <Label htmlFor={id} className={cn(error && "text-destructive")}>{getLiteral(label)}</Label>
      </div>
      {error && (
        <p className="text-[12px] font-medium text-destructive mt-0.5 animate-in fade-in slide-in-from-top-1 duration-200">
          {error}
        </p>
      )}
    </div>
  );
};
