import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { TextField as FluentTextField } from '@fluentui/react';

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

  const handleChange = (_e: React.FormEvent<HTMLInputElement | HTMLTextAreaElement>, nextValue?: string) => {
    const next = nextValue ?? '';
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

  const labelText = getLiteral(label);

  return (
    <div
      className="a2ui-field m-0"
      style={parseStyle(style)}
    >
      <FluentTextField
        id={id}
        type={password ? 'password' : 'text'}
        value={localVal}
        label={labelText || undefined}
        placeholder={getLiteral(placeholder)}
        errorMessage={error || undefined}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
      />
    </div>
  );
};
