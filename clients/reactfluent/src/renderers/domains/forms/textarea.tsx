import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { TextField as FluentTextField } from '@fluentui/react';

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
  const rootRef = React.useRef<HTMLDivElement | null>(null);
  const minHeight = Math.max(60, Number(rows) * 22 + 16);

  const resizeToContent = React.useCallback(() => {
    if (!auto_resize) return;
    const textarea = rootRef.current?.querySelector('textarea');
    if (!textarea) return;
    textarea.style.height = `${minHeight}px`;
    textarea.style.height = `${Math.max(minHeight, textarea.scrollHeight)}px`;
  }, [auto_resize, minHeight]);

  React.useEffect(() => {
    const next = getLiteral(value) || '';
    setLocalVal((prev) => (prev === next ? prev : next));
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  React.useLayoutEffect(() => {
    resizeToContent();
  }, [localVal, resizeToContent]);

  const handleChange = (_e: React.FormEvent<HTMLInputElement | HTMLTextAreaElement>, nextValue?: string) => {
    const next = nextValue ?? '';
    setLocalVal(next);
    setInput?.(id, next);
    
    if (onChangeAction) {
      emitActionSpec(onChangeAction, onAction, {
        [id]: next,
        value: next,
      });
    }
  };

  const labelText = getLiteral(label);

  return (
    <div
      ref={rootRef}
      className={`ds-field ds-textarea-field${auto_resize ? ' ds-textarea-field-autoresize' : ''}`}
      style={parseStyle(style)}
    >
      <FluentTextField
        className="ds-textarea"
        id={id}
        value={localVal}
        label={labelText || undefined}
        placeholder={getLiteral(placeholder)}
        disabled={disabled}
        multiline
        resizable
        rows={rows}
        errorMessage={error || undefined}
        onChange={handleChange}
        styles={{
          fieldGroup: {
            height: 'auto',
          },
          field: {
            minHeight,
            height: auto_resize ? minHeight : undefined,
            overflowY: auto_resize ? 'hidden' : undefined,
            resize: auto_resize ? 'none' : 'vertical',
          },
        }}
      />
    </div>
  );
};
