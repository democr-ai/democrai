import React from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from 'react-native';
import { emitActionSpec, getLiteral, isAnyTrackedActionPending, normalizeOptions } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

const valuesEqual = (left: any, right: any): boolean => JSON.stringify(left) === JSON.stringify(right);

const resolveItemSchema = (schema: any): { type: 'text' | 'select'; options: Array<{ label: string; value: string }> } => {
  const source = schema && typeof schema === 'object' && !Array.isArray(schema) ? schema : { type: 'text' };
  const type = String(source.type || 'text').trim().toLowerCase();
  if (type !== 'select') return { type: 'text', options: [] };
  return { type: 'select', options: normalizeOptions(source.options).map((option) => ({ label: option.label, value: String(option.value) })) };
};

export const EditableList: React.FC<any> = ({
  id,
  value = [],
  item_schema,
  item_label,
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
  const valueSignature = React.useMemo(() => JSON.stringify(Array.isArray(value) ? value.map(String) : []), [value]);
  const initialItems = React.useMemo(() => (Array.isArray(value) ? value.map(String) : []), [valueSignature]);
  const [items, setItems] = React.useState<string[]>(initialItems);
  const itemsRef = React.useRef<string[]>(initialItems);
  const lastPublishedInput = React.useRef<string | null>(null);
  const lastComponentIdRef = React.useRef(id);
  const lastExternalValueRef = React.useRef(valueSignature);
  const schema = React.useMemo(() => resolveItemSchema(item_schema), [item_schema]);
  const actionName = typeof action === 'string' ? action : String(action?.name || '');
  const isLoading = isAnyTrackedActionPending(pendingActions, track_loading, actionName);

  const publishInput = React.useCallback((next: string[]) => {
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
  }, [id, initialItems, publishInput, syncInitialInput, valueSignature]);

  const publishItems = (next: string[]) => {
    if (valuesEqual(itemsRef.current, next)) return;
    itemsRef.current = next;
    setItems(next);
    publishInput(next);
  };

  const updateItem = (index: number, nextValue: string) => {
    publishItems(itemsRef.current.map((item, itemIndex) => (itemIndex === index ? nextValue : item)));
  };

  const removeItem = (index: number) => {
    publishItems(itemsRef.current.filter((_item, itemIndex) => itemIndex !== index));
  };

  const newItemValue = () => {
    if (schema.type === 'select') return schema.options[0]?.value || '';
    return '';
  };

  const submit = () => {
    emitActionSpec(action, onAction, {
      ...(params && typeof params === 'object' && !Array.isArray(params) ? params : {}),
      [id]: itemsRef.current,
      value: itemsRef.current,
    });
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(item_label) ? <Text style={styles.label}>{getLiteral(item_label)}</Text> : null}
      <View style={styles.list}>
        {items.map((item, index) => (
          <View key={`${id}_${index}`} style={styles.row}>
            {schema.type === 'select' ? (
              <View style={styles.optionWrap}>
                {schema.options.map((option) => {
                  const selected = option.value === item;
                  return (
                    <TouchableOpacity
                      key={option.value}
                      style={[styles.option, selected && styles.optionSelected]}
                      onPress={() => updateItem(index, option.value)}
                    >
                      <Text style={[styles.optionText, selected && styles.optionTextSelected]}>{option.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            ) : (
              <TextInput
                style={styles.input}
                value={item}
                placeholder={getLiteral(placeholder)}
                placeholderTextColor="#6E7681"
                onChangeText={(next) => updateItem(index, next)}
              />
            )}
            <TouchableOpacity
              style={styles.removeButton}
              onPress={() => removeItem(index)}
              accessibilityLabel={getLiteral(remove_label || 'Remove')}
            >
              <Icon name="ri-delete-bin-line" size={17} color="#FF7B72" />
            </TouchableOpacity>
          </View>
        ))}
      </View>
      <View style={styles.actions}>
        <TouchableOpacity style={styles.secondaryButton} onPress={() => publishItems([...itemsRef.current, newItemValue()])}>
          <Icon name="ri-add-line" size={16} color="#58A6FF" />
          <Text style={styles.secondaryButtonText}>{getLiteral(add_label || 'Add')}</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.primaryButton, isLoading && styles.buttonDisabled]} onPress={submit} disabled={isLoading}>
          {isLoading ? <Icon name="ri-loader-4-line" size={16} color="#E6EDF3" /> : null}
          <Text style={styles.primaryButtonText}>{getLiteral(submit_label || 'Save')}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { width: '100%', marginVertical: 6 },
  label: { fontSize: 13, fontWeight: '500', color: '#8B949E', marginBottom: 6 },
  list: { gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  input: {
    flex: 1,
    height: 38,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    paddingHorizontal: 10,
    color: '#E6EDF3',
    backgroundColor: '#161B22',
  },
  optionWrap: { flex: 1, flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  option: { borderWidth: 1, borderColor: '#30363D', borderRadius: 7, paddingHorizontal: 10, paddingVertical: 8 },
  optionSelected: { borderColor: '#58A6FF', backgroundColor: '#1F6FEB26' },
  optionText: { color: '#C9D1D9', fontSize: 13 },
  optionTextSelected: { color: '#58A6FF', fontWeight: '600' },
  removeButton: {
    width: 38,
    height: 38,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#3B2226',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#2A1216',
  },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  secondaryButton: {
    minHeight: 36,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  secondaryButtonText: { color: '#58A6FF', fontSize: 13, fontWeight: '600' },
  primaryButton: {
    minHeight: 36,
    borderRadius: 8,
    backgroundColor: '#238636',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  buttonDisabled: { opacity: 0.55 },
  primaryButtonText: { color: '#E6EDF3', fontSize: 13, fontWeight: '600' },
});
