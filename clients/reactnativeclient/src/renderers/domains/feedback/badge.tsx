import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { getLiteral } from '../../shared';

const BADGE_VARIANTS = {
  default: { bg: 'rgba(113, 113, 122, 0.15)', text: '#71717a' },
  success: { bg: 'rgba(16, 185, 129, 0.15)', text: '#059669' },
  warning: { bg: 'rgba(245, 158, 11, 0.15)', text: '#d97706' },
  destructive: { bg: 'rgba(239, 68, 68, 0.15)', text: '#dc2626' },
  info: { bg: 'rgba(59, 130, 246, 0.15)', text: '#2563eb' },
};

export const Badge: React.FC<any> = ({ text, variant = 'default', style }) => {
  const normalized = String(variant || 'default').toLowerCase();
  const colors = (BADGE_VARIANTS as any)[normalized] || BADGE_VARIANTS.default;

  return (
    <View style={[
      styles.container,
      { backgroundColor: colors.bg },
      style
    ]}>
      <Text style={[styles.text, { color: colors.text }]}>
        {getLiteral(text)}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 9999,
    alignSelf: 'flex-start',
  },
  text: {
    fontSize: 12,
    fontWeight: '600',
  },
});
