import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { getLiteral, normalizeOptions, emitActionSpec } from '../../shared';

export const RadioGroup: React.FC<any> = ({
  id,
  label,
  options = [],
  value,
  action,
  onAction,
  setInput,
  style,
  error,
}) => {
  const normalized = React.useMemo(() => normalizeOptions(options), [options]);
  const [selected, setSelected] = React.useState(value == null ? '' : String(value));

  React.useEffect(() => {
    setSelected(value == null ? '' : String(value));
  }, [value]);

  const handleChange = (next: string) => {
    setSelected(next);
    setInput?.(id, next);
    emitActionSpec(action, onAction, { [id]: next, value: next });
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? (
        <Text style={[styles.label, error && styles.labelError]}>
          {getLiteral(label)}
        </Text>
      ) : null}
      <View style={styles.group}>
        {normalized.map((option, index) => {
          const optionValue = String(option.value);
          const isSelected = selected === optionValue;
          return (
            <TouchableOpacity
              key={`${id}_radio_${index}`}
              style={styles.option}
              onPress={() => handleChange(optionValue)}
              activeOpacity={0.7}
            >
              <View style={[
                styles.circle, 
                isSelected && styles.circleSelected,
                error && styles.circleError
              ]}>
                {isSelected && <View style={styles.innerCircle} />}
              </View>
              <Text style={[styles.optionLabel, error && styles.labelError]}>
                {option.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginVertical: 6,
  },
  label: {
    fontSize: 13,
    fontWeight: '500',
    color: '#8B949E',
    marginBottom: 8,
  },
  labelError: {
    color: '#FF7B72',
  },
  group: {
    gap: 8,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 4,
  },
  circle: {
    width: 20,
    height: 20,
    borderRadius: 10,
    borderWidth: 2,
    borderColor: '#30363D',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  circleSelected: {
    borderColor: '#58A6FF',
  },
  circleError: {
    borderColor: '#F85149',
  },
  innerCircle: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: '#58A6FF',
  },
  optionLabel: {
    fontSize: 15,
    color: '#C9D1D9',
  },
  errorText: {
    fontSize: 12,
    color: '#FF7B72',
    marginTop: 4,
  },
});
