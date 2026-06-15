import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, isAnyTrackedActionPending } from '@/renderers/shared';
import { Button, FormGroup, Input, Label } from 'design-react-kit';

const toStringList = (value: any): string[] => {
  if (!Array.isArray(value)) {
    throw new Error('EditableList value must be an array.');
  }
  if (value.some((item) => typeof item !== 'string')) {
    throw new Error('EditableList value items must be strings.');
  }
  return value;
};

const valuesEqual = (left: any, right: any): boolean => JSON.stringify(left) === JSON.stringify(right);

const resolveItemSchema = (schema: any): { type: 'text' | 'select'; options: Array<{ label: string; value: string }> } => {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) {
    throw new Error('EditableList item_schema must be an object.');
  }
  const type = String(schema.type || '').trim().toLowerCase();
  if (type === 'text') return { type, options: [] };
  if (type !== 'select') {
    throw new Error('EditableList item_schema type must be text or select.');
  }
  if (!Array.isArray(schema.options)) {
    throw new Error('EditableList select item_schema options must be an array.');
  }
  const options = schema.options.map((option: any) => {
    if (!option || typeof option !== 'object' || typeof option.label !== 'string' || typeof option.value !== 'string') {
      throw new Error('EditableList select options must have string label and value.');
    }
    return { label: option.label, value: option.value };
  });
  return { type, options };
};

export const EditableList: React.FC<any> = ({
  id,
  value = [],
  item_schema,
  item_label,
  label,
  add_label,
  remove_label,
  submit_label,
  placeholder,
  action,
  params = {},
  onAction,
  setInput,
  style,
  pendingActions,
  track_loading,
  syncInitialInput = true,
}) => {
  const valueSignature = React.useMemo(() => JSON.stringify(value), [value]);
  const initialItems = React.useMemo(() => toStringList(value), [valueSignature]);
  const [items, setItems] = React.useState<string[]>(initialItems);
  const lastPublishedInput = React.useRef<string | null>(null);
  const schema = resolveItemSchema(item_schema);
  const actionName = typeof action === 'string' ? action : String(action?.name || '');
  const isLoading = isAnyTrackedActionPending(pendingActions, track_loading, actionName);
  const fieldLabel = getLiteral(item_label ?? label);
  const addText = getLiteral(add_label, 'Add');
  const removeText = getLiteral(remove_label, 'Remove');
  const submitText = getLiteral(submit_label, 'Save');

  const publishInput = React.useCallback((next: string[]) => {
    const serialized = JSON.stringify(next);
    if (lastPublishedInput.current === serialized) return;
    lastPublishedInput.current = serialized;
    setInput?.(id, next);
  }, [id, setInput]);

  React.useEffect(() => {
    setItems((prev) => (valuesEqual(prev, initialItems) ? prev : initialItems));
    if (syncInitialInput) publishInput(initialItems);
  }, [initialItems, publishInput, syncInitialInput]);

  const publishItems = (next: string[]) => {
    setItems((prev) => (valuesEqual(prev, next) ? prev : next));
    publishInput(next);
  };

  const updateItem = (index: number, nextValue: string) => {
    const next = items.map((item, itemIndex) => (itemIndex === index ? nextValue : item));
    publishItems(next);
  };

  const removeItem = (index: number) => {
    publishItems(items.filter((_item, itemIndex) => itemIndex !== index));
  };

  const submit = () => {
    emitActionSpec(action, onAction, {
      ...(params && typeof params === 'object' && !Array.isArray(params) ? params : {}),
      [id]: items,
      value: items,
    });
  };

  const newItemValue = () => {
    if (schema.type === 'text') return '';
    if (schema.options.length === 0) {
      throw new Error('EditableList select item_schema requires at least one option.');
    }
    return schema.options[0].value;
  };

  return (
    <FormGroup className="a2ui-field a2ui-editable-list" style={parseStyle(style)}>
      {fieldLabel ? <Label>{fieldLabel}</Label> : null}
      <div className="a2ui-editable-list-rows">
        {items.map((item, index) => (
          <div key={`${id}_${index}`} className="a2ui-editable-list-row">
            <span className="a2ui-editable-list-index" aria-hidden="true">{index + 1}</span>
            {schema.type === 'select' ? (
              <Input
                type="select"
                tag="select"
                value={item}
                aria-label={`${fieldLabel || 'Item'} ${index + 1}`}
                className="a2ui-editable-list-control a2ui-select a2ui-select-single"
                onChange={(event: React.ChangeEvent<HTMLSelectElement>) => updateItem(index, event.target.value)}
              >
                {schema.options.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Input>
            ) : (
              <Input
                value={item}
                placeholder={getLiteral(placeholder)}
                aria-label={`${fieldLabel || 'Item'} ${index + 1}`}
                className="a2ui-editable-list-control"
                onChange={(event: React.ChangeEvent<HTMLInputElement>) => updateItem(index, event.target.value)}
              />
            )}
            <Button
              type="button"
              color="danger"
              size="sm"
              onClick={() => removeItem(index)}
              title={removeText}
              aria-label={removeText}
              className="a2ui-button a2ui-editable-list-remove flex-shrink-0"
            >
              <i className="ri-delete-bin-2-line" aria-hidden="true" />
            </Button>
          </div>
        ))}
      </div>
      <div className="a2ui-editable-list-actions d-flex flex-wrap gap-2 mt-3">
        <Button type="button" color="secondary" size="sm" outline className="a2ui-button" onClick={() => publishItems([...items, newItemValue()])}>
          {addText}
        </Button>
        <Button type="button" color="primary" size="sm" className="a2ui-button" onClick={submit} disabled={isLoading}>
          {isLoading ? <i className="ri-loader-4-line ri-spin me-1" /> : null}
          {submitText}
        </Button>
      </div>
    </FormGroup>
  );
};
