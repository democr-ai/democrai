import React from 'react';
import { Combobox as FluentCombobox, Field, Option } from '@fluentui/react-components';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '@/renderers/shared';

export const Combobox: React.FC<any> = ({
  id,
  label,
  options = [],
  value,
  placeholder,
  action,
  onAction,
  setInput,
  style,
  syncInitialInput = true,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const [query, setQuery] = React.useState('');
  const [selected, setSelected] = React.useState(value == null ? '' : String(value));

  React.useEffect(() => {
    const next = value == null ? '' : String(value);
    setSelected(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const selectedLabel = normalized.find((entry) => String(entry.value) === selected)?.label || '';
  const filtered = React.useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle || query === selectedLabel) return normalized;
    return normalized.filter((entry) => entry.label.toLowerCase().includes(needle));
  }, [normalized, query, selectedLabel]);

  return (
    <Field label={label ? getLiteral(label) : undefined} style={parseStyle(style)}>
      <FluentCombobox
        id={id}
        className="a2ui-combobox"
        placeholder={getLiteral(placeholder || 'Search...')}
        value={query || selectedLabel}
        selectedOptions={selected ? [selected] : []}
        onChange={(event) => setQuery(event.target.value)}
        onOptionSelect={async (_event, data) => {
          const next = data.optionValue == null ? '' : String(data.optionValue);
          if (!next || next === selected) {
            setQuery(selectedLabel);
            return;
          }
          if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
            setQuery(selectedLabel);
            return;
          }
          const nextLabel = normalized.find((entry) => String(entry.value) === next)?.label || '';
          setSelected(next);
          setQuery(nextLabel);
          setInput?.(id, next);
          const actionWithoutConfirm = action && typeof action === 'object'
            ? { ...action, confirm: undefined }
            : action;
          emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
        }}
        onBlur={() => setQuery(selectedLabel)}
      >
        {filtered.length > 0 ? filtered.map((entry, index) => (
          <Option
            key={`${id}_combo_${index}`}
            value={String(entry.value)}
            text={entry.label}
          >
            {entry.label}
          </Option>
        )) : (
          <Option disabled value="__empty__" text="No results">
            No results
          </Option>
        )}
      </FluentCombobox>
    </Field>
  );
};
