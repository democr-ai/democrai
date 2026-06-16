import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { getLiteral, toBoolean, emitActionSpec } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

export const Checkbox: React.FC<any> = ({ id, label, checked, action, onAction, setInput, style, error }) => {
  const [local, setLocal] = React.useState(toBoolean(checked));

  React.useEffect(() => {
    setLocal(toBoolean(checked));
  }, [checked]);

  const toggle = () => {
    const next = !local;
    setLocal(next);
    setInput?.(id, next);
    emitActionSpec(action, onAction, { [id]: next, checked: next, value: next });
  };

  return (
    <View style={[styles.container, style]}>
      <TouchableOpacity 
        style={styles.touchable} 
        onPress={toggle}
        activeOpacity={0.7}
      >
        <View style={[
          styles.box, 
          local && styles.boxChecked,
          error && styles.boxError
        ]}>
          {local && <Icon name="ri-check-line" size={16} color="#FFFFFF" />}
        </View>
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
  touchable: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  box: {
    width: 20,
    height: 20,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 4,
    backgroundColor: '#161B22',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 8,
  },
  boxChecked: {
    backgroundColor: '#1F6FEB',
    borderColor: '#1F6FEB',
  },
  boxError: {
    borderColor: '#F85149',
  },
  label: {
    fontSize: 13,
    color: '#C9D1D9',
  },
  labelError: {
    color: '#FF7B72',
  },
  errorText: {
    fontSize: 12,
    color: '#FF7B72',
    marginLeft: 28,
    marginTop: 4,
  },
});
