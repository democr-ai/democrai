import React from 'react';
import { View, Text, TextInput, StyleSheet } from 'react-native';
import { getLiteral } from '../../shared';

export const TextArea: React.FC<any> = ({
  id,
  label,
  value,
  placeholder,
  auto_resize = true,
  disabled = false,
  rows = 3,
  onChangeAction,
  onAction,
  setInput,
  style,
  error,
}) => {
  const [localVal, setLocalVal] = React.useState(getLiteral(value) || '');

  React.useEffect(() => {
    const next = getLiteral(value) || '';
    setLocalVal((prev) => (prev === next ? prev : next));
  }, [value]);

  const handleChange = (next: string) => {
    setLocalVal(next);
    setInput?.(id, next);
    
    if (onChangeAction?.name && onAction) {
      onAction(onChangeAction.name, {
        ...(onChangeAction.context || {}),
        [id]: next,
        value: next,
      });
    }
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? (
        <Text style={[styles.label, error && styles.labelError]}>
          {getLiteral(label)}
        </Text>
      ) : null}
      <TextInput
        style={[
          styles.input, 
          { minHeight: Math.max(80, rows * 20) },
          error && styles.inputError
        ]}
        value={localVal}
        placeholder={getLiteral(placeholder)}
        onChangeText={handleChange}
        multiline
        numberOfLines={rows}
        editable={!disabled}
        placeholderTextColor="#6E7681"
        textAlignVertical="top"
      />
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
  input: {
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    backgroundColor: '#161B22',
    color: '#E6EDF3',
  },
  inputError: {
    borderColor: '#F85149',
    backgroundColor: '#2A1216',
  },
  errorText: {
    fontSize: 12,
    color: '#FF7B72',
    marginTop: 4,
  },
});
