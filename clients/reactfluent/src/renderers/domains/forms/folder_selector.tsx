import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm } from '@/renderers/shared';
import { Button, Field, Input } from '@fluentui/react-components';

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
    <Field className="a2ui-field" style={parseStyle(style)} label={getLiteral(label || 'Folder')}>
      <div className="d-flex gap-2">
        <Input
          id={id}
          value={localValue}
          placeholder={getLiteral(placeholder || 'Folder path')}
          onChange={(e: any) => setLocalValue(e.target.value)}
          onBlur={(e: any) => { void commit(e.target.value); }}
          onKeyDown={(e: any) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void commit((e.target as HTMLInputElement).value);
            }
          }}
        />
        <Button
          type="button"
          appearance="secondary"
          size="small"
          disabled
          title="System folder browsing is not available in the browser client"
        >
          Browse
        </Button>
      </div>
    </Field>
  );
};
