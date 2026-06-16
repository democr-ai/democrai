import React from 'react';
import { View, Text, StyleSheet, ViewStyle } from 'react-native';
import { getLiteral } from '../../shared';
import { parseStyle } from '../../../utils/style';
import { usePhoneLayout, useResponsiveStyle } from '../../../utils/responsive';

const ALERT_VARIANTS = {
  info: { border: '#388BFD', bg: '#1C2736', text: '#79C0FF' },
  success: { border: '#3FB950', bg: '#1C2A1E', text: '#56D364' },
  warning: { border: '#D29922', bg: '#2A1E0F', text: '#E3B341' },
  destructive: { border: '#F85149', bg: '#2A1216', text: '#FF7B72' },
  default: { border: '#30363D', bg: '#1C2128', text: '#C9D1D9' },
};

export const Alert: React.FC<any> = ({ title, description, variant = 'info', style }) => {
  const normalized = String(variant || 'info').toLowerCase();
  const colors = (ALERT_VARIANTS as any)[normalized] || ALERT_VARIANTS.info;
  const isPhone = usePhoneLayout();
  const responsiveStyle = useResponsiveStyle(parseStyle(style) as ViewStyle, { clampFixedWidth: true });
  const safeStyle = React.useMemo(() => {
    const next: ViewStyle = { ...(responsiveStyle as ViewStyle) };
    if (isPhone) {
      delete next.minWidth;
      delete next.maxWidth;
      next.width = '96%';
      next.alignSelf = 'center';
      next.flexShrink = 1;
    }
    return next;
  }, [isPhone, responsiveStyle]);
  const titleText = getLiteral(title);
  const descriptionText = getLiteral(description);

  return (
    <View style={[
      styles.container,
      { backgroundColor: colors.bg, borderColor: colors.border },
      safeStyle as ViewStyle,
    ]}>
      {titleText ? (
        <Text style={[styles.title, { color: colors.text }]} numberOfLines={0}>
          {titleText}
        </Text>
      ) : null}
      {descriptionText ? (
        <Text style={[styles.description, { color: colors.text }]} numberOfLines={0}>
          {descriptionText}
        </Text>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignSelf: 'stretch',
    minWidth: 0,
    flexShrink: 1,
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    marginVertical: 4,
    overflow: 'hidden',
  },
  title: {
    flexShrink: 1,
    minWidth: 0,
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 4,
  },
  description: {
    flexShrink: 1,
    minWidth: 0,
    fontSize: 14,
    lineHeight: 20,
    opacity: 0.9,
  },
});
