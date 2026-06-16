import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { getLiteral, normalizeOptions, emitActionSpec, requestActionConfirm } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

const arraysEqual = (a: string[], b: string[]): boolean => {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
};

export const Select: React.FC<any> = ({
  id,
  label,
  options = [],
  value,
  placeholder,
  multiple,
  action,
  onAction,
  setInput,
  style,
  error,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const isMultiple = Boolean(multiple);
  const normalizedMultiValue = React.useMemo(() => {
    if (!isMultiple) return [] as string[];
    if (Array.isArray(value)) return value.map((item) => String(item));
    if (value == null || value === '') return [] as string[];
    return [String(value)];
  }, [isMultiple, value]);

  const [open, setOpen] = React.useState(false);
  const [localValue, setLocalValue] = React.useState(value == null ? '' : String(value));
  const [localValues, setLocalValues] = React.useState<string[]>(normalizedMultiValue);
  const lastExternalSingleRef = React.useRef<string>(value == null ? '' : String(value));
  const lastExternalMultiRef = React.useRef<string>(normalizedMultiValue.join('\u0001'));

  React.useEffect(() => {
    if (isMultiple) {
      const externalKey = normalizedMultiValue.join('\u0001');
      if (externalKey !== lastExternalMultiRef.current) {
        lastExternalMultiRef.current = externalKey;
        setLocalValues((prev) => (arraysEqual(prev, normalizedMultiValue) ? prev : normalizedMultiValue));
      }
      return;
    }
    const next = value == null ? '' : String(value);
    if (next !== lastExternalSingleRef.current) {
      lastExternalSingleRef.current = next;
      setLocalValue((prev) => (prev === next ? prev : next));
    }
  }, [isMultiple, normalizedMultiValue, value]);

  React.useEffect(() => {
    if (!id) return;
    setInput?.(id, isMultiple ? localValues : localValue);
  }, [id, isMultiple, localValue, localValues, setInput]);

  const actionWithoutConfirm = action && typeof action === 'object'
    ? { ...action, confirm: undefined }
    : action;

  const commitSingle = async (next: string) => {
    if (localValue === next) {
      setOpen(false);
      return;
    }
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      setOpen(false);
      return;
    }
    setLocalValue(next);
    setInput?.(id, next);
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
    setOpen(false);
  };

  const commitMultiple = async (next: string[]) => {
    if (arraysEqual(localValues, next)) return;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) return;
    setLocalValues(next);
    setInput?.(id, next);
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
  };

  const toggleMultipleValue = (rawValue: string) => {
    const target = String(rawValue);
    const order = new Map(normalized.map((entry, index) => [String(entry.value), index]));
    const nextSet = new Set(localValues);
    if (nextSet.has(target)) nextSet.delete(target);
    else nextSet.add(target);
    const next = Array.from(nextSet).sort((left, right) => {
      const leftPos = order.get(left) ?? Number.MAX_SAFE_INTEGER;
      const rightPos = order.get(right) ?? Number.MAX_SAFE_INTEGER;
      return leftPos - rightPos;
    });
    commitMultiple(next);
  };

  const selectedLabel = normalized.find((entry) => String(entry.value) === localValue)?.label || '';

  if (isMultiple) {
    return (
      <View style={[styles.container, style]}>
        {getLiteral(label) ? (
          <Text style={[styles.label, error && styles.labelError]}>{getLiteral(label)}</Text>
        ) : null}

        <View style={[styles.optionsContainer, styles.multiContainer, error && styles.inputError]}>
          <ScrollView keyboardShouldPersistTaps="handled" nestedScrollEnabled>
            {normalized.map((option, index) => {
              const optionValue = String(option.value);
              const isSelected = localValues.includes(optionValue);
              return (
                <TouchableOpacity
                  key={`${id}_multi_opt_${index}`}
                  style={[styles.option, isSelected && styles.optionSelected]}
                  onPress={() => toggleMultipleValue(optionValue)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.optionLabel, isSelected && styles.optionLabelSelected]}>{option.label}</Text>
                  <View style={[styles.checkbox, isSelected && styles.checkboxSelected]}>
                    {isSelected ? <Icon name="ri-check-line" size={14} color="#FFFFFF" /> : null}
                  </View>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>

        {error ? <Text style={styles.errorText}>{error}</Text> : null}
      </View>
    );
  }

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? (
        <Text style={[styles.label, error && styles.labelError]}>
          {getLiteral(label)}
        </Text>
      ) : null}

      <TouchableOpacity
        style={[styles.trigger, error && styles.inputError]}
        onPress={() => setOpen((prev) => !prev)}
        activeOpacity={0.75}
      >
        <Text style={[styles.triggerText, !selectedLabel && styles.placeholder]}>
          {selectedLabel || getLiteral(placeholder || 'Select an option')}
        </Text>
        <Icon name={open ? 'ri-arrow-up-s-line' : 'ri-arrow-down-s-line'} size={20} color="#8B949E" />
      </TouchableOpacity>

      {open ? (
        <View style={[styles.optionsContainer, styles.popover]}>
          <ScrollView keyboardShouldPersistTaps="handled" nestedScrollEnabled>
            {normalized.map((option, index) => {
              const optionValue = String(option.value);
              const isSelected = localValue === optionValue;
              return (
                <TouchableOpacity
                  key={`${id}_opt_${index}`}
                  style={[styles.option, isSelected && styles.optionSelected]}
                  onPress={() => commitSingle(optionValue)}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.optionLabel, isSelected && styles.optionLabelSelected]}>{option.label}</Text>
                  {isSelected ? <Icon name="ri-check-line" size={18} color="#58A6FF" /> : null}
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      ) : null}

      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginVertical: 6,
    width: '100%',
  },
  label: {
    fontSize: 13,
    fontWeight: '500',
    color: '#8B949E',
    marginBottom: 6,
  },
  labelError: {
    color: '#FF7B72',
  },
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
  triggerText: {
    flex: 1,
    color: '#E6EDF3',
    fontSize: 15,
  },
  placeholder: {
    color: '#6E7681',
  },
  optionsContainer: {
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#0D1117',
    overflow: 'hidden',
  },
  popover: {
    marginTop: 6,
    maxHeight: 220,
  },
  multiContainer: {
    minHeight: 96,
    maxHeight: 240,
    padding: 6,
  },
  inputError: {
    borderColor: '#F85149',
    backgroundColor: '#2A1216',
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderRadius: 6,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 10,
  },
  optionSelected: {
    backgroundColor: '#1F6FEB26',
  },
  optionLabel: {
    flex: 1,
    fontSize: 15,
    color: '#C9D1D9',
  },
  optionLabelSelected: {
    color: '#58A6FF',
    fontWeight: '600',
  },
  checkbox: {
    width: 20,
    height: 20,
    borderRadius: 5,
    borderWidth: 1,
    borderColor: '#30363D',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#161B22',
  },
  checkboxSelected: {
    borderColor: '#1F6FEB',
    backgroundColor: '#1F6FEB',
  },
  errorText: {
    fontSize: 12,
    color: '#FF7B72',
    marginTop: 4,
  },
});
