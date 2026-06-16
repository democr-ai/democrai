import React from 'react';
import { parseStyle } from '@/utils/style';

const coerceTextValue = (value: any, fallback: any = ''): string => {
  if (value == null) value = fallback;
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value && typeof value === 'object' && typeof value.literalString === 'string') return value.literalString;
  if (value && typeof value === 'object') {
    const defaultValue = (value as any).default;
    if (typeof defaultValue === 'string' || typeof defaultValue === 'number' || typeof defaultValue === 'boolean') {
      return String(defaultValue);
    }
  }
  if (typeof fallback === 'string' || typeof fallback === 'number' || typeof fallback === 'boolean') return String(fallback);
  return '';
};

export const Text: React.FC<any> = ({ text, style, align = 'left', selectable = false, muted = false, tone = 'default' }) => {
  const normalizedTone = String(tone || 'default').trim().toLowerCase();
  const isMuted = muted === true || normalizedTone === 'muted' || normalizedTone === 'secondary';

  const alignClass = align === 'center' ? 'text-center' : (align === 'right' ? 'text-end' : '');
  const colorClass = isMuted ? 'text-muted' : '';
  const selectClass = selectable ? '' : 'user-select-none';

  return (
    <div
      className={`small text-break text-wrap ${alignClass} ${colorClass} ${selectClass}`}
      style={{ ...parseStyle(style), whiteSpace: 'pre-wrap' }}
    >
      {coerceTextValue(text, '')}
    </div>
  );
};
