import React from 'react';
import { StyleSheet, Text, View, type ViewStyle } from 'react-native';
import QRCodeSvg from 'react-native-qrcode-svg';
import { getLiteral } from '../../shared';
import { parseStyle } from '../../../utils/style';

const toColor = (value: any, fallback: string): string => {
  const raw = getLiteral(value, '').trim();
  if (!raw || raw.startsWith('var(')) return fallback;
  return raw;
};

const toSize = (value: any): number => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 220;
  return Math.max(40, Math.min(320, parsed));
};

export const QRCode: React.FC<any> = ({
  content,
  value,
  size = 220,
  style,
  fill_color = '#0D1117',
  back_color = '#FFFFFF',
}) => {
  const text = getLiteral(content || value);
  const safeSize = toSize(size);
  const foreground = toColor(fill_color, '#0D1117');
  const background = toColor(back_color, '#FFFFFF');
  const parsedStyle = parseStyle(style) as ViewStyle;

  return (
    <View style={[styles.container, parsedStyle]}>
      <View style={[styles.qrFrame, { backgroundColor: background }]}>
        {text ? (
          <QRCodeSvg
            value={text}
            size={safeSize}
            color={foreground}
            backgroundColor={background}
          />
        ) : (
          <Text style={styles.empty}>[QR: empty content]</Text>
        )}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignSelf: 'center',
    maxWidth: '100%',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#161B22',
    padding: 14,
    marginVertical: 4,
    overflow: 'hidden',
  },
  qrFrame: {
    maxWidth: '100%',
    borderRadius: 6,
    overflow: 'hidden',
    padding: 8,
  },
  empty: {
    minWidth: 120,
    minHeight: 80,
    color: '#8B949E',
    fontSize: 12,
    textAlign: 'center',
    textAlignVertical: 'center',
  },
});
