import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm } from '@/renderers/shared';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

export const FolderSelector: React.FC<any> = ({
  id,
  label,
  value,
  placeholder,
  action,
  onAction,
  setInput,
  style,
  syncInitialInput = true,
}) => {
  const [localValue, setLocalValue] = React.useState(getLiteral(value));
  const committedValueRef = React.useRef(getLiteral(value));

  React.useEffect(() => {
    const next = getLiteral(value);
    committedValueRef.current = next;
    setLocalValue(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const commit = async (next: string) => {
    if (next === committedValueRef.current) return;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      setLocalValue(committedValueRef.current);
      return;
    }
    committedValueRef.current = next;
    setLocalValue(next);
    setInput?.(id, next);
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
  };

  return (
    <div className="grid gap-1.5" style={parseStyle(style)}>
      <Label>{getLiteral(label || 'Folder')}</Label>
      <div className="flex gap-2">
        <Input
          value={localValue}
          placeholder={getLiteral(placeholder || 'Folder path')}
          onChange={(e) => setLocalValue(e.target.value)}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commit((e.target as HTMLInputElement).value);
            }
          }}
        />
        <Button
          type="button"
          variant="outline"
          disabled
          title="System folder browsing is not available in the browser client"
        >
          Browse
        </Button>
      </div>
    </div>
  );
};
