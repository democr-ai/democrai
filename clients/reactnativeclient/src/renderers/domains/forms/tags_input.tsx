import React from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from 'react-native';
import { emitActionSpec, getLiteral, normalizeOptions } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

type TagsItemSchema = {
  type: 'text' | 'string' | 'number' | 'boolean' | 'select';
  options?: Array<{ label: string; value: any }>;
};

const valuesEqual = (left: any, right: any): boolean => JSON.stringify(left) === JSON.stringify(right);

const normalizeItems = (value: any): any[] => {
  if (Array.isArray(value)) return value;
  if (value == null || value === '') return [];
  return [value];
};

const normalizeSchema = (schema: any): TagsItemSchema => {
  const source = schema && typeof schema === 'object' && !Array.isArray(schema) ? schema : { type: 'text' };
  const type = String(source.type || 'text').trim().toLowerCase();
  if (type === 'select') return { type, options: normalizeOptions(source.options) };
  if (['text', 'string', 'number', 'boolean'].includes(type)) return { type: type as TagsItemSchema['type'] };
  return { type: 'text' };
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
    return Number.isFinite(value) ? value : undefined;
  }
  if (schema.type === 'boolean') return raw === 'true';
  if (schema.type === 'select') {
    const option = (schema.options || [])[Number(raw)];
    return option ? option.value : undefined;
  }
  const text = String(raw || '').trim();
  return text || undefined;
};

export const TagsInput: React.FC<any> = ({
  id,
  label,
  value,
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
  const valueSignature = React.useMemo(() => JSON.stringify(normalizeItems(value)), [value]);
  const initialItems = React.useMemo(() => normalizeItems(value), [valueSignature]);
  const [items, setItems] = React.useState<any[]>(initialItems);
  const [draft, setDraft] = React.useState(schema.type === 'boolean' ? 'true' : '0');
  const itemsRef = React.useRef<any[]>(initialItems);
  const lastPublishedInput = React.useRef<string | null>(null);
  const lastComponentIdRef = React.useRef(id);
  const lastExternalValueRef = React.useRef(valueSignature);

  const publishInput = React.useCallback((next: any[]) => {
    const serialized = JSON.stringify(next);
    if (lastPublishedInput.current === serialized) return;
    lastPublishedInput.current = serialized;
    setInput?.(id, next);
  }, [id, setInput]);

  React.useEffect(() => {
    if (lastComponentIdRef.current === id && lastExternalValueRef.current === valueSignature) return;
    lastComponentIdRef.current = id;
    lastExternalValueRef.current = valueSignature;
    itemsRef.current = initialItems;
    setItems(initialItems);
    lastPublishedInput.current = JSON.stringify(initialItems);
    if (syncInitialInput) publishInput(initialItems);
  }, [id, initialItems, publishInput, syncInitialInput]);

  React.useEffect(() => {
    if (schema.type === 'boolean') setDraft('true');
    else if (schema.type === 'select') setDraft('0');
    else setDraft('');
  }, [schema.type]);

  const publishItems = React.useCallback((next: any[]) => {
    const normalizedNext = normalizeItems(next);
    if (valuesEqual(itemsRef.current, normalizedNext)) return false;
    itemsRef.current = normalizedNext;
    setItems(normalizedNext);
    publishInput(normalizedNext);
    if (action) {
      emitActionSpec(action, onAction, {
        ...(params && typeof params === 'object' && !Array.isArray(params) ? params : {}),
        [id]: normalizedNext,
        value: normalizedNext,
      });
    }
    return true;
  }, [action, id, items, onAction, params, publishInput]);

  const addItem = () => {
    const nextValue = candidateValue(schema, draft);
    if (nextValue === undefined) return;
    const current = itemsRef.current;
    if (current.some((item) => valuesEqual(item, nextValue))) return;
    const added = publishItems([...current, nextValue]);
    if (added && (schema.type === 'text' || schema.type === 'string' || schema.type === 'number')) setDraft('');
  };

  const removeItem = (index: number) => {
    publishItems(itemsRef.current.filter((_item, itemIndex) => itemIndex !== index));
  };

  const renderPicker = () => {
    if (schema.type === 'boolean') {
      return (
        <View style={styles.segment}>
          {['true', 'false'].map((entry) => (
            <TouchableOpacity key={entry} style={[styles.segmentItem, draft === entry && styles.segmentItemActive]} onPress={() => setDraft(entry)}>
              <Text style={[styles.segmentText, draft === entry && styles.segmentTextActive]}>{entry}</Text>
            </TouchableOpacity>
          ))}
        </View>
      );
    }
    if (schema.type === 'select') {
      return (
        <View style={styles.options}>
          {(schema.options || []).map((option, index) => {
            const selected = draft === String(index);
            return (
              <TouchableOpacity key={`${id}_tag_option_${index}`} style={[styles.option, selected && styles.optionActive]} onPress={() => setDraft(String(index))}>
                <Text style={[styles.optionText, selected && styles.optionTextActive]}>{option.label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
      );
    }
    return (
      <TextInput
        style={styles.input}
        value={draft}
        placeholder={getLiteral(placeholder)}
        placeholderTextColor="#6E7681"
        keyboardType={schema.type === 'number' ? 'numeric' : 'default'}
        onChangeText={setDraft}
        onSubmitEditing={addItem}
      />
    );
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? <Text style={[styles.label, error && styles.labelError]}>{getLiteral(label)}</Text> : null}
      <View style={[styles.chips, error && styles.inputError]}>
        {items.map((item, index) => (
          <View key={`${id}_tag_${index}`} style={styles.chip}>
            <Text style={styles.chipText}>{itemText(schema, item)}</Text>
            <TouchableOpacity onPress={() => removeItem(index)} hitSlop={8}>
              <Icon name="ri-close-line" size={14} color="#8B949E" />
            </TouchableOpacity>
          </View>
        ))}
        {!items.length ? <Text style={styles.empty}>No tags</Text> : null}
      </View>
      <View style={styles.addRow}>
        <View style={styles.addControl}>{renderPicker()}</View>
        <TouchableOpacity style={styles.addButton} onPress={addItem} activeOpacity={0.75}>
          <Icon name="ri-add-line" size={16} color="#E6EDF3" />
          <Text style={styles.addButtonText}>{getLiteral(add_label || 'Add')}</Text>
        </TouchableOpacity>
      </View>
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { width: '100%', marginVertical: 6 },
  label: { fontSize: 13, fontWeight: '500', color: '#8B949E', marginBottom: 6 },
  labelError: { color: '#FF7B72' },
  chips: {
    minHeight: 44,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    padding: 8,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  inputError: { borderColor: '#F85149', backgroundColor: '#2A1216' },
  chip: {
    maxWidth: '100%',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 6,
    backgroundColor: '#21262D',
    paddingHorizontal: 8,
    paddingVertical: 5,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  chipText: { color: '#E6EDF3', fontSize: 13 },
  empty: { color: '#6E7681', fontSize: 13, paddingVertical: 4 },
  addRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginTop: 8 },
  addControl: { flex: 1 },
  input: {
    height: 38,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    paddingHorizontal: 10,
    color: '#E6EDF3',
    backgroundColor: '#0D1117',
  },
  addButton: {
    minHeight: 38,
    borderRadius: 8,
    backgroundColor: '#238636',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  addButtonText: { color: '#E6EDF3', fontSize: 13, fontWeight: '600' },
  segment: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    overflow: 'hidden',
  },
  segmentItem: { flex: 1, minHeight: 38, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0D1117' },
  segmentItemActive: { backgroundColor: '#1F6FEB26' },
  segmentText: { color: '#8B949E', fontSize: 13 },
  segmentTextActive: { color: '#58A6FF', fontWeight: '600' },
  options: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  option: { borderWidth: 1, borderColor: '#30363D', borderRadius: 7, paddingHorizontal: 10, paddingVertical: 8 },
  optionActive: { borderColor: '#58A6FF', backgroundColor: '#1F6FEB26' },
  optionText: { color: '#C9D1D9', fontSize: 13 },
  optionTextActive: { color: '#58A6FF', fontWeight: '600' },
  errorText: { fontSize: 12, color: '#FF7B72', marginTop: 4 },
});
