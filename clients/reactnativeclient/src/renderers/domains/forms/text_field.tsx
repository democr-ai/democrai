import React from 'react';
import { View, Text, TextInput, StyleSheet } from 'react-native';
import { getLiteral, emitActionSpec } from '../../shared';

export const TextField: React.FC<any> = ({
  label,
  value,
  placeholder,
  action,
  onChangeAction,
  onAction,
  id,
  style,
  setInput,
  password,
  onChangeMode,
  error,
  autoCapitalize,
  keyboardType,
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
      const changeMode = String(onChangeMode || 'local').trim().toLowerCase();
      if (['live', 'autocomplete', 'search', 'search_suggest', 'remote_validate', 'remote_preview'].includes(changeMode)) {
        onAction(onChangeAction.name, {
          ...(onChangeAction.context || {}),
          [id]: next,
          value: next,
        });
      }
    }
  };

  const handleSubmit = () => {
    emitActionSpec(action, onAction, {
      [id]: localVal,
      value: localVal,
    });
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? (
        <Text style={[styles.label, error && styles.labelError]}>
          {getLiteral(label)}
        </Text>
      ) : null}
      <TextInput
        style={[styles.input, error && styles.inputError]}
        value={localVal}
        placeholder={getLiteral(placeholder)}
        onChangeText={handleChange}
        onSubmitEditing={handleSubmit}
        secureTextEntry={password}
        autoCapitalize={autoCapitalize ?? 'none'}
        autoCorrect={password ? false : undefined}
        keyboardType={keyboardType}
        placeholderTextColor="#6E7681"
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
    height: 42,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    paddingHorizontal: 12,
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
