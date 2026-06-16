import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, requestActionConfirm } from '@/renderers/shared';
import { Field, Input } from '@/design/system';

const TOKEN_CHARS = new Set(['y', 'M', 'd', 'H', 'm']);

const countMaskDigits = (format: string): number => [...format].filter((ch) => TOKEN_CHARS.has(ch)).length;

const applyMask = (raw: string, format: string): string => {
  const digits = String(raw || '').replace(/\D/g, '').slice(0, countMaskDigits(format));
  let digitIndex = 0;
  let output = '';

  for (const ch of format) {
    if (TOKEN_CHARS.has(ch)) {
      if (digitIndex >= digits.length) break;
      output += digits[digitIndex];
      digitIndex += 1;
      continue;
    }
    if (digitIndex === 0 || digitIndex > digits.length) break;
    output += ch;
  }

  return output;
};

const buildRegex = (format: string): RegExp => {
  const escaped = format.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = escaped
    .replace(/yyyy/g, '(?<yyyy>\\d{4})')
    .replace(/MM/g, '(?<MM>\\d{2})')
    .replace(/dd/g, '(?<dd>\\d{2})')
    .replace(/HH/g, '(?<HH>\\d{2})')
    .replace(/mm/g, '(?<mm>\\d{2})');
  return new RegExp(`^${pattern}$`);
};

const parseDateTime = (value: string, format: string): Date | null => {
  const regex = buildRegex(format);
  const match = regex.exec(value);
  if (!match?.groups) return null;

  const year = Number(match.groups.yyyy ?? 0);
  const month = Number(match.groups.MM ?? 1);
  const day = Number(match.groups.dd ?? 1);
  const hour = Number(match.groups.HH ?? 0);
  const minute = Number(match.groups.mm ?? 0);

  if (!Number.isFinite(year) || year < 1) return null;
  if (!Number.isFinite(month) || month < 1 || month > 12) return null;
  if (!Number.isFinite(day) || day < 1 || day > 31) return null;
  if (!Number.isFinite(hour) || hour < 0 || hour > 23) return null;
  if (!Number.isFinite(minute) || minute < 0 || minute > 59) return null;

  const dt = new Date(year, month - 1, day, hour, minute, 0, 0);
  if (dt.getFullYear() !== year) return null;
  if (dt.getMonth() !== month - 1) return null;
  if (dt.getDate() !== day) return null;
  if (dt.getHours() !== hour) return null;
  if (dt.getMinutes() !== minute) return null;
  return dt;
};

const isComplete = (value: string, format: string): boolean => value.length === format.length;

export const DatePicker: React.FC<any> = ({
  id,
  label,
  value,
  min_date,
  max_date,
  format = 'yyyy-MM-dd',
  action,
  onAction,
  setInput,
  style,
  error,
  syncInitialInput = true,
}) => {
  const maskFormat = String(format || 'yyyy-MM-dd');
  const [localValue, setLocalValue] = React.useState(applyMask(getLiteral(value), maskFormat));
  const [localError, setLocalError] = React.useState('');

  React.useEffect(() => {
    const next = applyMask(getLiteral(value), maskFormat);
    setLocalValue((prev) => (prev === next ? prev : next));
    if (syncInitialInput) setInput?.(id, next);
  }, [id, maskFormat, setInput, syncInitialInput, value]);

  const validate = React.useCallback((next: string): string => {
    if (!next || !isComplete(next, maskFormat)) return '';
    const parsed = parseDateTime(next, maskFormat);
    if (!parsed) return 'Invalid date format.';

    const minRaw = getLiteral(min_date);
    const maxRaw = getLiteral(max_date);
    const minParsed = minRaw ? parseDateTime(minRaw, maskFormat) : null;
    const maxParsed = maxRaw ? parseDateTime(maxRaw, maskFormat) : null;

    if (minParsed && parsed < minParsed) return `Value must be >= ${minRaw}.`;
    if (maxParsed && parsed > maxParsed) return `Value must be <= ${maxRaw}.`;
    return '';
  }, [maskFormat, max_date, min_date]);

  const commit = async (raw: string) => {
    const next = applyMask(raw, maskFormat);
    if (next === localValue) return;
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) {
      return;
    }
    const validationError = validate(next);
    setLocalValue(next);
    setLocalError(validationError);
    setInput?.(id, next);
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
  };

  const shownError = getLiteral(error) || localError;
  const labelText = getLiteral(label);
  const hasTime = /H|m/.test(maskFormat);

  return (
    <Field
      className="ds-field ds-date-picker"
      label={labelText || undefined}
      validationState={shownError ? 'error' : undefined}
      validationMessage={shownError || undefined}
      style={parseStyle(style)}
    >
      <div className={`ds-date-picker-control${hasTime ? ' ds-date-picker-control-time' : ''}`}>
        <Input
          id={id}
          value={localValue}
          placeholder={maskFormat}
          inputMode="numeric"
          className="ds-date-picker-input"
          contentBefore={<i className={hasTime ? 'ri-time-line' : 'ri-calendar-line'} aria-hidden="true" />}
          onChange={(e) => { void commit(e.target.value); }}
        />
      </div>
    </Field>
  );
};
