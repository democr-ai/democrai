import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { getLiteral, emitActionSpec, toBoolean } from '../../shared';

export const Breadcrumb: React.FC<any> = ({
  segments,
  items,
  action,
  onAction,
  separator = '/',
  style,
}) => {
  const normalizedSegments = Array.isArray(segments)
    ? segments
    : Array.isArray(items)
      ? items
      : [];
  const separatorText = getLiteral(separator, '/');

  return (
    <View style={[styles.container, style]}>
      {normalizedSegments.map((segment: any, index: number) => {
        const isLast = index === normalizedSegments.length - 1;
        const current = toBoolean(segment?.current) || isLast;
        const label = getLiteral(segment?.label || segment?.title);
        const path = segment?.path;
        const canNavigate = !current && Boolean(path);
        const fallbackAction = path ? { name: 'navigate', context: { path } } : action;
        
        return (
          <View key={`bc_${index}`} style={styles.item}>
            <TouchableOpacity
              onPress={() => emitActionSpec(segment?.action || fallbackAction, onAction, { item: segment, segment, index, path })}
              disabled={!canNavigate && !segment?.action && !action}
              activeOpacity={0.7}
              hitSlop={{ top: 6, right: 6, bottom: 6, left: 6 }}
            >
              <Text style={[styles.label, current && styles.labelCurrent, !canNavigate && !segment?.action && !action && styles.labelDisabled]}>
                {label}
              </Text>
            </TouchableOpacity>
            {!isLast && (
              <Text style={styles.separator}>{separatorText}</Text>
            )}
          </View>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    flexWrap: 'wrap',
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  label: {
    fontSize: 14,
    lineHeight: 20,
    color: '#58A6FF',
  },
  labelCurrent: {
    color: '#E6EDF3',
    fontWeight: '600',
  },
  labelDisabled: {
    color: '#8B949E',
  },
  separator: {
    marginHorizontal: 8,
    color: '#8B949E',
    fontSize: 14,
    lineHeight: 20,
  },
});
