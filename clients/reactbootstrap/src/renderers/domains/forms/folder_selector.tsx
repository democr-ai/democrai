import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm } from '@/renderers/shared';
import { Label, Input, Button, FormGroup } from 'design-react-kit';

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
    <FormGroup style={parseStyle(style)}>
      <Label for={id}>{getLiteral(label || 'Cartella')}</Label>
      <div className="d-flex gap-2">
        <Input
          id={id}
          value={localValue}
          placeholder={getLiteral(placeholder || 'Percorso cartella')}
          onChange={(e: any) => setLocalValue(e.target.value)}
          onBlur={(e: any) => commit(e.target.value)}
          onKeyDown={(e: any) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commit((e.target as HTMLInputElement).value);
            }
          }}
        />
        <Button
          type="button"
          outline
          color="secondary"
          disabled
          title="La navigazione delle cartelle di sistema non è disponibile nel client browser"
        >
          Sfoglia
        </Button>
      </div>
    </FormGroup>
  );
};
