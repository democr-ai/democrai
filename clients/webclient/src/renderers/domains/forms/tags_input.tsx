import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { cn } from '@/lib/utils';

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
      return (
        <select value={draft} onChange={(event) => setDraft(event.target.value)} className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs">
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
    }
    if (schema.type === 'select') {
      if (!schema.options || schema.options.length === 0) throw new Error('TagsInput select item_schema requires at least one option.');
      return (
        <select value={draft} onChange={(event) => setDraft(event.target.value)} className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs">
          {schema.options.map((option, index) => (
            <option key={`${id}_opt_${index}`} value={String(index)}>{option.label}</option>
          ))}
        </select>
      );
    }
    return (
      <Input
        type={schema.type === 'number' ? 'number' : 'text'}
        value={draft}
        placeholder={getLiteral(placeholder)}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== 'Enter') return;
          event.preventDefault();
          addItem();
        }}
      />
    );
  };

  return (
    <div className="grid gap-2" style={parseStyle(style)}>
      {getLiteral(label) ? <Label className={cn(error && 'text-destructive')}>{getLiteral(label)}</Label> : null}
      <div className={cn('flex min-h-10 flex-wrap items-center gap-2 rounded-md border border-input bg-background p-2 shadow-xs', error && 'border-destructive/50 bg-destructive/5')}>
        {items.map((item, index) => (
          <span key={`${id}_tag_${index}`} className="inline-flex max-w-full items-center gap-1 rounded-md border bg-muted px-2 py-1 text-sm">
            <span className="truncate">{itemText(schema, item)}</span>
            <button type="button" className="text-muted-foreground hover:text-foreground" onClick={() => removeItem(index)}>x</button>
          </span>
        ))}
      </div>
      <div className="flex min-w-0 gap-2">
        <div className="min-w-0 flex-1">{control()}</div>
        <Button type="button" variant="outline" size="sm" onClick={addItem}>{getLiteral(add_label || 'Add')}</Button>
      </div>
      {error ? <p className="text-[12px] font-medium text-destructive">{error}</p> : null}
    </div>
  );
};
