import React from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from 'react-native';
import { emitActionSpec, getLiteral, requestActionConfirm } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const FolderSelector: React.FC<any> = ({
  id,
  label,
  value,
  placeholder,
  action,
  onAction,
  setInput,
  style,
  syncInitialInput = true,
}) => {
  const [localValue, setLocalValue] = React.useState(getLiteral(value));
  const committedValueRef = React.useRef(getLiteral(value));

  React.useEffect(() => {
    const next = getLiteral(value);
    committedValueRef.current = next;
    setLocalValue(next);
    if (syncInitialInput) setInput?.(id, next);
  }, [id, setInput, syncInitialInput, value]);

  const commit = async (next: string) => {
    if (next === committedValueRef.current) return;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      setLocalValue(committedValueRef.current);
      return;
    }
    committedValueRef.current = next;
    setLocalValue(next);
    setInput?.(id, next);
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
  };

  return (
    <View style={[styles.container, style]}>
      <Text style={styles.label}>{getLiteral(label || 'Folder')}</Text>
      <View style={styles.row}>
        <TextInput
          style={styles.input}
          value={localValue}
          placeholder={getLiteral(placeholder || 'Folder path')}
          placeholderTextColor="#6E7681"
          onChangeText={setLocalValue}
          onBlur={() => commit(localValue)}
          onSubmitEditing={() => commit(localValue)}
          autoCapitalize="none"
        />
        <TouchableOpacity style={styles.button} disabled>
          <Icon name="ri-folder-open-line" size={18} color="#6E7681" />
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { width: '100%', marginVertical: 6 },
  label: { fontSize: 13, fontWeight: '500', color: '#8B949E', marginBottom: 6 },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  input: {
    flex: 1,
    height: 42,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 15,
    backgroundColor: '#161B22',
    color: '#E6EDF3',
  },
  button: {
    width: 42,
    height: 42,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#161B22',
    opacity: 0.75,
  },
});
