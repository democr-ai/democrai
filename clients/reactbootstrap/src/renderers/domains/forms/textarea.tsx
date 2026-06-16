import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { FormGroup, Label, Input, FormFeedback } from 'design-react-kit';

export const TextArea: React.FC<any> = ({
  id,
  label,
  value,
  placeholder,
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

  const labelText = getLiteral(label);

  return (
    <FormGroup className="a2ui-field" style={parseStyle(style)}>
      {labelText ? (
        <Label for={id}>
          {labelText}
        </Label>
      ) : null}
      <Input
        id={id}
        type="textarea"
        tag="textarea"
        value={localVal}
        placeholder={getLiteral(placeholder)}
        disabled={disabled}
        rows={rows}
        onChange={handleChange}
        valid={error ? false : undefined}
      />
      {error && <FormFeedback>{error}</FormFeedback>}
    </FormGroup>
  );
};
