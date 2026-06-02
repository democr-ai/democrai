import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';
import { Label } from '@/components/ui/label';
import { RadioGroup as UIRadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { cn } from '@/lib/utils';

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

  const handleChange = async (next: string) => {
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

  return (
    <div className="grid gap-2" style={parseStyle(style)}>
      <Label className={cn(error && 'text-destructive')}>{getLiteral(label)}</Label>
      <UIRadioGroup value={selected} onValueChange={handleChange} className="grid gap-2">
        {normalized.map((option, index) => {
          const optionValue = String(option.value);
          const optionLabel = option.label;
          return (
            <div key={`${id}_radio_${index}`} className="flex items-center gap-2">
              <RadioGroupItem id={`${id}_radio_${index}`} value={optionValue} className={cn(error && 'border-destructive/50 text-destructive')} />
              <Label htmlFor={`${id}_radio_${index}`} className={cn(error && 'text-destructive/80')}>
                {optionLabel}
              </Label>
            </div>
          );
        })}
      </UIRadioGroup>
      {error && (
        <p className="text-[12px] font-medium text-destructive mt-1 animate-in fade-in slide-in-from-top-1 duration-200">
          {error}
        </p>
      )}
    </div>
  );
};
