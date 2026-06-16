import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { getLiteral, toBoolean } from '../../shared';

export const Progress: React.FC<any> = ({ value = 0, maximum = 100, label, show_label = true, style }) => {
  const safeMaximum = Math.max(1, Number(maximum) || 100);
  const safeValue = Math.max(0, Math.min(Number(value) || 0, safeMaximum));
  const pct = Math.round((safeValue / safeMaximum) * 100);

  return (
    <View style={[styles.container, style]}>
      {toBoolean(show_label) ? (
        <View style={styles.labelContainer}>
          <Text style={styles.label}>{getLiteral(label)}</Text>
          <Text style={styles.percentage}>{pct}%</Text>
        </View>
      ) : null}
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${pct}%` }]} />
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginVertical: 8,
    width: '100%',
  },
  labelContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  label: {
    fontSize: 14,
    color: '#374151',
  },
  percentage: {
    fontSize: 14,
    color: '#6b7280',
  },
  track: {
    height: 8,
    backgroundColor: '#e5e7eb',
    borderRadius: 4,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    backgroundColor: '#3b82f6',
  },
});
