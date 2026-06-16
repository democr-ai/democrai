import React from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from 'react-native';
import { emitActionSpec, getLiteral, requestActionConfirm } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

const pad2 = (value: number): string => String(value).padStart(2, '0');
const sameDay = (left: Date, right: Date): boolean => (
  left.getFullYear() === right.getFullYear() &&
  left.getMonth() === right.getMonth() &&
  left.getDate() === right.getDate()
);

const dateKey = (date: Date): string => `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;

const parseLooseDate = (raw: string): Date | null => {
  const value = String(raw || '').trim();
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4] || 0);
  const minute = Number(match[5] || 0);
  const dt = new Date(year, month - 1, day, hour, minute, 0, 0);
  if (dt.getFullYear() !== year || dt.getMonth() !== month - 1 || dt.getDate() !== day) return null;
  return dt;
};

const formatValue = (date: Date, format: string, time: { hour: string; minute: string }): string => {
  const withDate = format
    .replace(/yyyy/g, String(date.getFullYear()))
    .replace(/MM/g, pad2(date.getMonth() + 1))
    .replace(/dd/g, pad2(date.getDate()));
  return withDate
    .replace(/HH/g, pad2(Number(time.hour) || 0))
    .replace(/mm/g, pad2(Number(time.minute) || 0));
};

const monthDays = (cursor: Date): Date[] => {
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - first.getDay());
  return Array.from({ length: 42 }, (_entry, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    return date;
  });
};

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
  const includesTime = /H|m/.test(maskFormat);
  const parsedInitial = parseLooseDate(getLiteral(value)) || new Date();
  const [open, setOpen] = React.useState(false);
  const [cursor, setCursor] = React.useState(new Date(parsedInitial.getFullYear(), parsedInitial.getMonth(), 1));
  const [selected, setSelected] = React.useState(parsedInitial);
  const [time, setTime] = React.useState({
    hour: pad2(parsedInitial.getHours()),
    minute: pad2(parsedInitial.getMinutes()),
  });
  const [localError, setLocalError] = React.useState('');

  React.useEffect(() => {
    const next = parseLooseDate(getLiteral(value));
    if (!next) return;
    setSelected(next);
    setCursor(new Date(next.getFullYear(), next.getMonth(), 1));
    setTime({ hour: pad2(next.getHours()), minute: pad2(next.getMinutes()) });
    if (syncInitialInput) setInput?.(id, formatValue(next, maskFormat, { hour: pad2(next.getHours()), minute: pad2(next.getMinutes()) }));
  }, [id, maskFormat, setInput, syncInitialInput, value]);

  const validate = React.useCallback((date: Date): string => {
    const minRaw = getLiteral(min_date);
    const maxRaw = getLiteral(max_date);
    const minParsed = minRaw ? parseLooseDate(minRaw) : null;
    const maxParsed = maxRaw ? parseLooseDate(maxRaw) : null;
    if (minParsed && date < minParsed) return `Deve essere >= ${minRaw}.`;
    if (maxParsed && date > maxParsed) return `Deve essere <= ${maxRaw}.`;
    return '';
  }, [max_date, min_date]);

  const publish = async (date: Date, nextTime = time) => {
    const next = formatValue(date, maskFormat, nextTime);
    if (action?.confirm && !(await requestActionConfirm(action.confirm))) return;
    const validationError = validate(date);
    setSelected(date);
    setLocalError(validationError);
    setInput?.(id, next);
    const actionWithoutConfirm = action && typeof action === 'object' ? { ...action, confirm: undefined } : action;
    emitActionSpec(actionWithoutConfirm, onAction, { [id]: next, value: next });
  };

  const shownError = getLiteral(error) || localError;
  const displayValue = formatValue(selected, maskFormat, time);

  const updateTime = (part: 'hour' | 'minute', raw: string) => {
    const limit = part === 'hour' ? 23 : 59;
    const numeric = String(raw || '').replace(/\D/g, '').slice(0, 2);
    const clamped = numeric === '' ? '' : pad2(Math.min(limit, Number(numeric)));
    const next = { ...time, [part]: clamped };
    setTime(next);
    if (clamped.length === 2) publish(selected, next);
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? <Text style={[styles.label, shownError && styles.labelError]}>{getLiteral(label)}</Text> : null}
      <TouchableOpacity style={[styles.trigger, shownError && styles.inputError]} onPress={() => setOpen((prev) => !prev)} activeOpacity={0.75}>
        <Text style={styles.triggerText}>{displayValue || maskFormat}</Text>
        <Icon name={open ? 'ri-calendar-close-line' : 'ri-calendar-line'} size={18} color="#8B949E" />
      </TouchableOpacity>

      {open ? (
        <View style={styles.panel}>
          <View style={styles.nav}>
            <TouchableOpacity style={styles.iconButton} onPress={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))}>
              <Icon name="ri-arrow-left-s-line" size={20} color="#C9D1D9" />
            </TouchableOpacity>
            <Text style={styles.monthTitle}>{cursor.toLocaleDateString('en', { month: 'long', year: 'numeric' })}</Text>
            <TouchableOpacity style={styles.iconButton} onPress={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))}>
              <Icon name="ri-arrow-right-s-line" size={20} color="#C9D1D9" />
            </TouchableOpacity>
          </View>
          <View style={styles.weekRow}>
            {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((entry, index) => <Text key={`${entry}_${index}`} style={styles.weekText}>{entry}</Text>)}
          </View>
          <View style={styles.grid}>
            {monthDays(cursor).map((date) => {
              const muted = date.getMonth() !== cursor.getMonth();
              const active = sameDay(date, selected);
              const today = dateKey(date) === dateKey(new Date());
              return (
                <TouchableOpacity
                  key={dateKey(date)}
                  style={[styles.day, active && styles.dayActive, today && !active && styles.dayToday]}
                  onPress={() => publish(date)}
                  activeOpacity={0.75}
                >
                  <Text style={[styles.dayText, muted && styles.dayMuted, active && styles.dayTextActive]}>{date.getDate()}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {includesTime ? (
            <View style={styles.timeRow}>
              <Text style={styles.timeLabel}>Time</Text>
              <TextInput style={styles.timeInput} value={time.hour} keyboardType="number-pad" onChangeText={(next) => updateTime('hour', next)} />
              <Text style={styles.timeSep}>:</Text>
              <TextInput style={styles.timeInput} value={time.minute} keyboardType="number-pad" onChangeText={(next) => updateTime('minute', next)} />
            </View>
          ) : null}
        </View>
      ) : null}
      {shownError ? <Text style={styles.errorText}>{shownError}</Text> : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { width: '100%', marginVertical: 6 },
  label: { fontSize: 13, fontWeight: '500', color: '#8B949E', marginBottom: 6 },
  labelError: { color: '#FF7B72' },
  trigger: {
    minHeight: 42,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    paddingHorizontal: 12,
    backgroundColor: '#161B22',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  triggerText: { color: '#E6EDF3', fontSize: 15 },
  inputError: { borderColor: '#F85149', backgroundColor: '#2A1216' },
  panel: {
    marginTop: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#0D1117',
    padding: 10,
  },
  nav: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  iconButton: { width: 32, height: 32, borderRadius: 7, alignItems: 'center', justifyContent: 'center', backgroundColor: '#161B22' },
  monthTitle: { color: '#E6EDF3', fontSize: 14, fontWeight: '600' },
  weekRow: { flexDirection: 'row', marginBottom: 4 },
  weekText: { flex: 1, color: '#8B949E', fontSize: 11, textAlign: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  day: { width: `${100 / 7}%`, aspectRatio: 1.15, alignItems: 'center', justifyContent: 'center', borderRadius: 7 },
  dayToday: { borderWidth: 1, borderColor: '#30363D' },
  dayActive: { backgroundColor: '#1F6FEB' },
  dayText: { color: '#C9D1D9', fontSize: 13 },
  dayMuted: { color: '#484F58' },
  dayTextActive: { color: '#FFFFFF', fontWeight: '700' },
  timeRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  timeLabel: { color: '#8B949E', fontSize: 13, marginRight: 'auto' },
  timeInput: { width: 46, height: 34, borderRadius: 7, borderWidth: 1, borderColor: '#30363D', color: '#E6EDF3', textAlign: 'center', backgroundColor: '#161B22' },
  timeSep: { color: '#8B949E', fontSize: 16 },
  errorText: { fontSize: 12, color: '#FF7B72', marginTop: 4 },
});
