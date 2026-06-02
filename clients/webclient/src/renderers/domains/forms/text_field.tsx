import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

export const TextField: React.FC<any> = ({
  label,
  value,
  placeholder,
  action,
  onChangeAction,
  onAction,
  id,
  style,
  setInput,
  password,
  onChangeMode,
  error,
  syncInitialInput = true,
}) => {
  const [localVal, setLocalVal] = React.useState(getLiteral(value));

  React.useEffect(() => {
    const next = getLiteral(value);
    setLocalVal((prev) => (prev === next ? prev : next));
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const emitChangeAction = React.useCallback(
    (next: string) => {
      const changeMode = String(onChangeMode || 'local').trim().toLowerCase();
      if (!['live', 'autocomplete', 'search', 'search_suggest', 'remote_validate', 'remote_preview'].includes(changeMode)) {
        return;
      }
      emitActionSpec(onChangeAction, onAction, {
        [id]: next,
        value: next,
      });
    },
    [id, onAction, onChangeAction, onChangeMode],
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    setLocalVal(next);
    setInput?.(id, next);
    emitChangeAction(next);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    emitActionSpec(action, onAction, {
      [id]: localVal,
      value: localVal,
    });
  };

  return (
    <div className="grid gap-1.5" style={parseStyle(style)}>
      {getLiteral(label) ? (
        <Label className={cn(error && "text-destructive")}>
          {getLiteral(label)}
        </Label>
      ) : null}
      <Input
        type={password ? 'password' : 'text'}
        value={localVal}
        placeholder={getLiteral(placeholder)}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        className={cn(error && "border-destructive/50 focus-visible:ring-destructive/50 bg-destructive/5")}
      />
      {error && (
        <p className="text-[12px] font-medium text-destructive mt-0.5 animate-in fade-in slide-in-from-top-1 duration-200">
          {error}
        </p>
      )}
    </div>
  );
};
