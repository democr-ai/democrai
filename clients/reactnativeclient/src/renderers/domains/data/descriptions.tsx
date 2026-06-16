import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { getLiteral, toBoolean } from '../../shared';

export const Descriptions: React.FC<any> = ({
  model = [],
  data = {},
  key_header,
  value_header,
  borders = true,
  style,
}) => {
  const normalizedData = data && typeof data === 'object' ? data : {};
  const showBorders = toBoolean(borders);

  const fieldDefs = React.useMemo(() => {
    if (Array.isArray(model) && model.length > 0) {
      return model.filter((entry: any) => entry && typeof entry === 'object');
    }
    return Object.keys(normalizedData).map((key) => ({
      field: key,
      label: key.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase()),
    }));
  }, [model, normalizedData]);

  return (
    <View style={[
      styles.container, 
      showBorders && styles.bordered,
      style
    ]}>
      {(key_header || value_header) ? (
        <View style={[
          styles.row,
          styles.headerRow,
          showBorders && fieldDefs.length > 0 && styles.rowBorder,
        ]}>
          <View style={styles.keyCol}>
            <Text style={styles.headerText}>{getLiteral(key_header, 'Property')}</Text>
          </View>
          <View style={styles.valueCol}>
            <Text style={styles.headerText}>{getLiteral(value_header, 'Value')}</Text>
          </View>
        </View>
      ) : null}
      {fieldDefs.map((fieldDef: any, idx: number) => {
        const key = String(fieldDef.field || '').trim();
        if (!key) return null;
        const label = getLiteral(
          fieldDef.label ?? fieldDef.header,
          key.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase()),
        );
        const value = String(normalizedData[key] ?? '-');
        const isLast = idx === fieldDefs.length - 1;

        return (
          <View key={`${key}_${idx}`} style={[
            styles.row, 
            !isLast && showBorders && styles.rowBorder
          ]}>
            <View style={styles.keyCol}>
              <Text style={styles.keyText}>{label}</Text>
            </View>
            <View style={styles.valueCol}>
              <Text style={styles.valueText}>{value}</Text>
            </View>
          </View>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    backgroundColor: '#161B22',
    borderRadius: 8,
    overflow: 'hidden',
  },
  bordered: {
    borderWidth: 1,
    borderColor: '#30363D',
  },
  row: {
    flexDirection: 'row',
  },
  headerRow: {
    backgroundColor: '#21262D',
  },
  rowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
  },
  keyCol: {
    flex: 1,
    backgroundColor: '#1C2128',
    padding: 12,
    borderRightWidth: 1,
    borderRightColor: '#30363D',
  },
  valueCol: {
    flex: 2,
    padding: 12,
  },
  headerText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#E6EDF3',
  },
  keyText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#8B949E',
  },
  valueText: {
    fontSize: 14,
    color: '#E6EDF3',
  },
});
