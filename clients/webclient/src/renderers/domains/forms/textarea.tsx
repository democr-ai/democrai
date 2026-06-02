import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Textarea as UITextarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

export const TextArea: React.FC<any> = ({
  id,
  label,
  value,
  placeholder,
  auto_resize = true,
  disabled = false,
  rows = 3,
  onChangeAction,
  onAction,
  setInput,
  style,
  error,
  syncInitialInput = true,
}) => {
  const [localVal, setLocalVal] = React.useState(getLiteral(value) || '');

  React.useEffect(() => {
    const next = getLiteral(value) || '';
    setLocalVal((prev) => (prev === next ? prev : next));
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value;
    setLocalVal(next);
    setInput?.(id, next);
    
    if (onChangeAction) {
      emitActionSpec(onChangeAction, onAction, {
        [id]: next,
        value: next,
      });
    }
  };

  return (
    <div className="grid gap-1.5" style={parseStyle(style)}>
      {getLiteral(label) ? (
        <Label htmlFor={id} className={cn(error && "text-destructive")}>
          {getLiteral(label)}
        </Label>
      ) : null}
      <UITextarea
        id={id}
        value={localVal}
        placeholder={getLiteral(placeholder)}
        disabled={disabled}
        rows={rows}
        onChange={handleChange}
        className={cn(
          auto_resize ? 'field-sizing-content' : '',
          error && "border-destructive/50 focus-visible:ring-destructive/50 bg-destructive/5"
        )}
      />
      {error && (
        <p className="text-[12px] font-medium text-destructive mt-0.5 animate-in fade-in slide-in-from-top-1 duration-200">
          {error}
        </p>
      )}
    </div>
  );
};
