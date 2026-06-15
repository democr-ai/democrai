import React from 'react';
import { DefaultButton, Dropdown, TextField, type IDropdownOption } from '@fluentui/react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';

type TagsItemSchema = {
  type: 'text' | 'string' | 'number' | 'boolean' | 'select';
  options?: Array<{ label: string; value: any }>;
};

const valuesEqual = (left: any, right: any): boolean => JSON.stringify(left) === JSON.stringify(right);

const normalizeSchema = (schema: any): TagsItemSchema => {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) {
    throw new Error('TagsInput item_schema must be an object.');
  }
  const type = String(schema.type || '').trim().toLowerCase();
  if (!['text', 'string', 'number', 'boolean', 'select'].includes(type)) {
    throw new Error('TagsInput item_schema type must be text, string, number, boolean or select.');
  }
  if (type !== 'select') return { type: type as TagsItemSchema['type'] };
  if (!Array.isArray(schema.options)) {
    throw new Error('TagsInput select item_schema options must be an array.');
  }
  schema.options.forEach((option: any) => {
    if (!option || typeof option !== 'object' || typeof option.label !== 'string' || !Object.prototype.hasOwnProperty.call(option, 'value')) {
      throw new Error('TagsInput select options must have label and value.');
    }
  });
  return { type: 'select', options: schema.options };
};

const normalizeValue = (value: any): any[] => {
  if (!Array.isArray(value)) throw new Error('TagsInput value must be an array.');
  return value;
};

const itemText = (schema: TagsItemSchema, value: any): string => {
  if (schema.type === 'select') {
    const option = (schema.options || []).find((entry) => valuesEqual(entry.value, value));
    if (option) return option.label;
  }
  return String(value);
};

const candidateValue = (schema: TagsItemSchema, raw: string): any => {
  if (schema.type === 'number') {
    const value = Number(raw);
    if (!Number.isFinite(value)) return undefined;
    return value;
  }
  if (schema.type === 'boolean') return raw === 'true';
  if (schema.type === 'select') {
    const index = Number(raw);
    const option = (schema.options || [])[index];
    return option ? option.value : undefined;
  }
  const text = String(raw || '').trim();
  return text || undefined;
};

export const TagsInput: React.FC<any> = ({
  id,
  label,
  value = [],
  placeholder,
  add_label,
  item_schema,
  action,
  params,
  onAction,
  setInput,
  style,
  error,
  syncInitialInput = true,
}) => {
  const schema = React.useMemo(() => normalizeSchema(item_schema), [item_schema]);
  const valueSignature = React.useMemo(() => JSON.stringify(value), [value]);
  const initialItems = React.useMemo(() => normalizeValue(value), [valueSignature]);
  const [items, setItems] = React.useState<any[]>(initialItems);
  const [draft, setDraft] = React.useState(schema.type === 'boolean' ? 'true' : '0');
  const lastPublishedInput = React.useRef<string | null>(null);

  const publishInput = React.useCallback((next: any[]) => {
    const serialized = JSON.stringify(next);
    if (lastPublishedInput.current === serialized) return;
    lastPublishedInput.current = serialized;
    setInput?.(id, next);
  }, [id, setInput]);

  React.useEffect(() => {
    setItems((prev) => (valuesEqual(prev, initialItems) ? prev : initialItems));
    if (syncInitialInput) publishInput(initialItems);
  }, [initialItems, publishInput, syncInitialInput]);

  React.useEffect(() => {
    if (schema.type === 'boolean') setDraft('true');
    else if (schema.type === 'select') setDraft('0');
    else setDraft('');
  }, [schema.type]);

  const publish = (next: any[]) => {
    setItems((prev) => (valuesEqual(prev, next) ? prev : next));
    publishInput(next);
    if (action) {
      emitActionSpec(action, onAction, {
        ...(params && typeof params === 'object' && !Array.isArray(params) ? params : {}),
        [id]: next,
        value: next,
      });
    }
  };

  const addItem = () => {
    const nextValue = candidateValue(schema, draft);
    if (nextValue === undefined) return;
    if (items.some((item) => valuesEqual(item, nextValue))) return;
    publish([...items, nextValue]);
    if (schema.type === 'text' || schema.type === 'string' || schema.type === 'number') setDraft('');
  };

  const removeItem = (index: number) => {
    publish(items.filter((_item, itemIndex) => itemIndex !== index));
  };

  const control = () => {
    if (schema.type === 'boolean') {
      const options: IDropdownOption[] = [
        { key: 'true', text: 'true' },
        { key: 'false', text: 'false' },
      ];
      return (
        <Dropdown
          className="a2ui-tags-control"
          selectedKey={draft}
          options={options}
          onChange={(_event, option) => setDraft(String(option?.key ?? 'true'))}
        />
      );
    }
    if (schema.type === 'select') {
      if (!schema.options || schema.options.length === 0) throw new Error('TagsInput select item_schema requires at least one option.');
      const options: IDropdownOption[] = schema.options.map((option, index) => ({
        key: String(index),
        text: option.label,
      }));
      return (
        <Dropdown
          className="a2ui-tags-control"
          selectedKey={draft}
          options={options}
          onChange={(_event, option) => setDraft(String(option?.key ?? '0'))}
        />
      );
    }
    return (
      <TextField
        className="a2ui-tags-control"
        type={schema.type === 'number' ? 'number' : 'text'}
        value={draft}
        placeholder={getLiteral(placeholder)}
        onChange={(_event, nextValue) => setDraft(nextValue || '')}
        onKeyDown={(event: React.KeyboardEvent<HTMLInputElement>) => {
          if (event.key !== 'Enter') return;
          event.preventDefault();
          addItem();
        }}
      />
    );
  };

  return (
    <div className={`a2ui-field a2ui-tags-field ${error ? 'is-invalid' : ''}`} style={parseStyle(style)}>
      {getLiteral(label) ? <label className="a2ui-tags-label">{getLiteral(label)}</label> : null}
      <div className={`a2ui-tags-shell ${error ? 'is-invalid' : ''}`}>
        {items.length > 0 ? (
          <div className="a2ui-tags-list">
            {items.map((item, index) => (
              <span key={`${id}_tag_${index}`} className="a2ui-tags-chip">
                <span className="a2ui-tags-chip-text">{itemText(schema, item)}</span>
                <button
                  type="button"
                  className="a2ui-tags-chip-remove"
                  aria-label="Remove"
                  onClick={() => removeItem(index)}
                >
                  <i className="ri-close-line" aria-hidden="true" />
                </button>
              </span>
            ))}
          </div>
        ) : (
          <div className="a2ui-tags-empty">
            <i className="ri-price-tag-3-line" aria-hidden="true" />
            <span>{getLiteral(placeholder) || 'No tags yet'}</span>
          </div>
        )}
      </div>
      <div className="a2ui-tags-editor">
        <div className="a2ui-tags-editor-control">{control()}</div>
        <DefaultButton className="a2ui-tags-add" type="button" onClick={addItem}>
          <i className="ri-add-line" aria-hidden="true" />
          <span>{getLiteral(add_label || 'Add')}</span>
        </DefaultButton>
      </div>
      {error ? <div className="a2ui-tags-error">{error}</div> : null}
    </div>
  );
};
