import React from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import { emitActionSpec, getLiteral, normalizeOptions, requestActionConfirm } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

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
  error,
  syncInitialInput = true,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const [selected, setSelected] = React.useState(value == null ? '' : String(value));

  React.useEffect(() => {
    const next = value == null ? '' : String(value);
    setSelected(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const selectedLabel = normalized.find((entry) => String(entry.value) === selected)?.label || '';
  const filtered = normalized.filter((entry) => entry.label.toLowerCase().includes(query.trim().toLowerCase()));

  const choose = async (entry: { label: string; value: any }) => {
    const next = String(entry.value);
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      setOpen(false);
      return;
    }
    setSelected(next);
    setInput?.(id, next);
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
    setOpen(false);
    setQuery('');
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? <Text style={[styles.label, error && styles.labelError]}>{getLiteral(label)}</Text> : null}
      <TouchableOpacity
        style={[styles.trigger, error && styles.inputError]}
        onPress={() => setOpen((prev) => !prev)}
        activeOpacity={0.75}
      >
        <Text style={[styles.triggerText, !selectedLabel && styles.placeholder]}>
          {selectedLabel || getLiteral(placeholder || 'Search...')}
        </Text>
        <Icon name={open ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'} size={20} color="#8B949E" />
      </TouchableOpacity>
      {open ? (
        <View style={styles.popover}>
          <TextInput
            style={styles.search}
            value={query}
            placeholder="Search..."
            placeholderTextColor="#6E7681"
            onChangeText={setQuery}
            autoCapitalize="none"
          />
          <ScrollView style={styles.options} keyboardShouldPersistTaps="handled">
            {filtered.length ? filtered.map((entry, index) => {
              const isSelected = String(entry.value) === selected;
              return (
                <TouchableOpacity
                  key={`${id}_combo_${index}`}
                  style={[styles.option, isSelected && styles.optionSelected]}
                  onPress={() => choose(entry)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.optionText, isSelected && styles.optionTextSelected]}>{entry.label}</Text>
                  {isSelected ? <Icon name="ri-check-line" size={18} color="#58A6FF" /> : null}
                </TouchableOpacity>
              );
            }) : (
              <Text style={styles.noResults}>No results</Text>
            )}
          </ScrollView>
        </View>
      ) : null}
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { width: '100%', marginVertical: 6 },
  label: { fontSize: 13, fontWeight: '500', color: '#8B949E', marginBottom: 6 },
  labelError: { color: '#FF7B72' },
  trigger: {
    minHeight: 42,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  triggerText: { flex: 1, color: '#E6EDF3', fontSize: 15 },
  placeholder: { color: '#6E7681' },
  inputError: { borderColor: '#F85149', backgroundColor: '#2A1216' },
  popover: {
    marginTop: 6,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#0D1117',
    padding: 8,
  },
  search: {
    height: 38,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 7,
    paddingHorizontal: 10,
    color: '#E6EDF3',
    backgroundColor: '#161B22',
    marginBottom: 8,
  },
  options: { maxHeight: 220 },
  option: {
    minHeight: 38,
    borderRadius: 7,
    paddingHorizontal: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  optionSelected: { backgroundColor: '#1F6FEB26' },
  optionText: { color: '#C9D1D9', fontSize: 14 },
  optionTextSelected: { color: '#58A6FF', fontWeight: '600' },
  noResults: { color: '#6E7681', fontSize: 13, paddingHorizontal: 10, paddingVertical: 8 },
  errorText: { fontSize: 12, color: '#FF7B72', marginTop: 4 },
});
