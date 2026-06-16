import React from 'react';
import { Text as RNText, StyleSheet, TextStyle } from 'react-native';

const coerceTextValue = (value: any, fallback: any = ''): string => {
  if (value == null) return String(fallback || '');
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value && typeof value === 'object' && typeof value.literalString === 'string') return value.literalString;
  if (value && typeof value === 'object') {
    const defaultValue = (value as any).default;
    if (typeof defaultValue === 'string' || typeof defaultValue === 'number' || typeof defaultValue === 'boolean') {
      return String(defaultValue);
    }
  }
  return String(fallback || '');
};

export const Text: React.FC<any> = (props) => {
  const { text, label, value, content: body, style, variant, id, muted } = props;
  const rawText = text ?? label ?? value ?? body;
  const content = coerceTextValue(rawText, id ? `[Text:${id}]` : '');
  const normalizedId = String(id || '').toLowerCase();
  const isMuted = muted === true || String(muted || '').toLowerCase() === 'true';
  
  return (
    <RNText
      style={[
        styles.text,
        isMuted && styles.muted,
        styles[variant as keyof typeof styles],
        normalizedId === 'welcome_text' && styles.loginCenteredText,
        normalizedId === 'version_text' && styles.loginVersionText,
        style as TextStyle,
      ]}
    >
      {content}
    </RNText>
  );
};

export const Title: React.FC<any> = (props) => {
  const { text, label, value, title, style, level = 1, id } = props;
  const rawText = text ?? label ?? value ?? title;
  const levelStyle = styles[`h${level}` as keyof typeof styles] || styles.h1;
  const content = coerceTextValue(rawText, id ? `[Title:${id}]` : '');

  return (
    <RNText style={[styles.title, levelStyle, style as TextStyle]}>
      {content}
    </RNText>
  );
};

const styles = StyleSheet.create({
  text: {
    fontSize: 15,
    color: '#C9D1D9',
    lineHeight: 22,
  },
  title: {
    fontWeight: '700',
    color: '#E6EDF3',
  },
  h1: { fontSize: 30, marginBottom: 16, lineHeight: 38 },
  h2: { fontSize: 22, marginBottom: 12, lineHeight: 30 },
  h3: { fontSize: 18, marginBottom: 8, lineHeight: 26 },
  h4: { fontSize: 16, marginBottom: 6, lineHeight: 22 },
  h5: { fontSize: 14, marginBottom: 4, lineHeight: 20 },
  h6: { fontSize: 13, marginBottom: 4, lineHeight: 18 },
  primary: { color: '#6366F1' },
  secondary: { color: '#8B949E' },
  muted: { color: '#6E7681' },
  loginCenteredText: {
    width: '100%',
    textAlign: 'center',
  },
  loginVersionText: {
    width: '100%',
    textAlign: 'center',
    marginTop: 12,
  },
});
