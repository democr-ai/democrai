import React from 'react';
import { View, Text, Switch, StyleSheet, TouchableOpacity } from 'react-native';
import { getLiteral, emitActionSpec } from '../../shared';

export const Toggle: React.FC<any> = ({
  id,
  label,
  checked,
  action,
  onAction,
  setInput,
  style,
  error,
}) => {
  const [value, setValue] = React.useState(Boolean(checked));

  React.useEffect(() => {
    setValue(Boolean(checked));
  }, [checked]);

  const handleChange = (next: boolean) => {
    setValue(next);
    setInput?.(id, next);
    emitActionSpec(action, onAction, {
      [id]: next,
      checked: next,
      value: next,
    });
  };

  return (
    <View style={[styles.container, style]}>
      <TouchableOpacity 
        style={styles.row} 
        onPress={() => handleChange(!value)}
        activeOpacity={0.7}
      >
        <Switch
          value={value}
          onValueChange={handleChange}
          trackColor={{ false: '#30363D', true: '#1F6FEB' }}
          thumbColor={value ? '#E6EDF3' : '#8B949E'}
          ios_backgroundColor="#30363D"
          style={styles.switchControl}
        />
        <Text style={[styles.label, error && styles.labelError]}>
          {getLiteral(label)}
        </Text>
      </TouchableOpacity>
      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginVertical: 4,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  switchControl: {
    transform: [{ scaleX: 0.82 }, { scaleY: 0.82 }],
    marginLeft: -4,
    marginRight: -4,
  },
  label: {
    fontSize: 13,
    color: '#C9D1D9',
    flex: 1,
  },
  labelError: {
    color: '#FF7B72',
  },
  errorText: {
    fontSize: 12,
    color: '#FF7B72',
    marginTop: 4,
    marginLeft: 42,
  },
});
