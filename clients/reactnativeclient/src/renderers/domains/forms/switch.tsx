import React from 'react';
import { View, Text, Switch as RNSwitch, StyleSheet } from 'react-native';
import { getLiteral, toBoolean, emitActionSpec } from '../../shared';

export const Switch: React.FC<any> = ({ id, label, checked, action, onAction, setInput, style, error }) => {
  const [local, setLocal] = React.useState(toBoolean(checked));

  React.useEffect(() => {
    setLocal(toBoolean(checked));
  }, [checked]);

  const onChange = (next: boolean) => {
    setLocal(next);
    setInput?.(id, next);
    emitActionSpec(action, onAction, { [id]: next, checked: next, value: next });
  };

  return (
    <View style={[styles.container, style]}>
      <View style={styles.row}>
        <Text style={[styles.label, error && styles.labelError]}>
          {getLiteral(label)}
        </Text>
        <RNSwitch
          value={local}
          onValueChange={onChange}
          trackColor={{ false: '#30363D', true: '#1F6FEB' }}
          thumbColor={local ? '#E6EDF3' : '#8B949E'}
          ios_backgroundColor="#30363D"
          style={styles.switchControl}
        />
      </View>
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
    justifyContent: 'space-between',
  },
  label: {
    fontSize: 13,
    color: '#C9D1D9',
    flex: 1,
  },
  switchControl: {
    transform: [{ scaleX: 0.82 }, { scaleY: 0.82 }],
    marginLeft: 8,
    marginRight: -4,
  },
  labelError: {
    color: '#FF7B72',
  },
  errorText: {
    fontSize: 12,
    color: '#FF7B72',
    marginTop: 4,
  },
});
