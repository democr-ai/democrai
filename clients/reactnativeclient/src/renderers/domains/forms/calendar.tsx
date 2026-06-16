import React from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { emitActionSpec, getLiteral } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

const pad = (value: number): string => String(value).padStart(2, '0');
const dateKey = (date: Date): string => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
const TODAY = dateKey(new Date());

const MONTH_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const DAY_LONG = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const safeDate = (value: any): Date | null => {
  const raw = getLiteral(value);
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

const startOfMondayWeek = (date: Date): Date => {
  const day = date.getDay() || 7;
  return addDays(date, 1 - day);
};

const addDays = (date: Date, amount: number): Date => (
  new Date(date.getFullYear(), date.getMonth(), date.getDate() + amount)
);

const addMonths = (date: Date, amount: number): Date => (
  new Date(date.getFullYear(), date.getMonth() + amount, 1)
);

const addWeeks = (date: Date, amount: number): Date => addDays(date, amount * 7);

const sameMonth = (a: Date, b: Date): boolean => (
  a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
);

const fmtDate = (iso: string): string => {
  const parts = String(iso || '').split('-').map(Number);
  if (parts.length < 3 || parts.some(Number.isNaN)) return iso;
  return `${MONTH_SHORT[parts[1] - 1] || ''} ${parts[2]}`;
};

const buildHourSlots = (from: number, to: number): string[] => {
  const slots: string[] = [];
  for (let h = from; h < to; h += 1) slots.push(`${pad(h)}:00`);
  return slots;
};

const buildHalfHourSlots = (from: number, to: number): string[] => {
  const slots: string[] = [];
  for (let h = from; h < to; h += 1) {
    slots.push(`${pad(h)}:00`);
    slots.push(`${pad(h)}:30`);
  }
  return slots;
};

const eventDate = (event: any): string => (
  getLiteral(event?.date) || (typeof event?.start === 'string' ? event.start.slice(0, 10) : '')
);

const eventTime = (event: any): string => (
  getLiteral(event?.time) || (typeof event?.start === 'string' && event.start.length >= 16 ? event.start.slice(11, 16) : '')
);

const groupByDate = (events: any[]): Record<string, any[]> => {
  const grouped: Record<string, any[]> = {};
  (Array.isArray(events) ? events : []).forEach((event) => {
    const key = eventDate(event);
    if (!key) return;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(event);
  });
  Object.values(grouped).forEach((items) => {
    items.sort((a, b) => eventTime(a).localeCompare(eventTime(b)));
  });
  return grouped;
};

const normalizeView = (value: any): 'month' | 'week' | 'day' => {
  const raw = getLiteral(value).toLowerCase();
  return raw === 'week' || raw === 'day' ? raw : 'month';
};

const timeRange = (fromValue: any, toValue: any) => {
  const from = Math.max(0, Math.min(23, Number.parseInt(getLiteral(fromValue, '0'), 10) || 0));
  const to = Math.max(from + 1, Math.min(24, Number.parseInt(getLiteral(toValue, '24'), 10) || 24));
  return { from, to };
};

const ViewSwitch: React.FC<any> = ({ active, onChange }) => (
  <View style={styles.viewSwitch}>
    {[
      { key: 'month', label: 'Month' },
      { key: 'week', label: 'Week' },
      { key: 'day', label: 'Day' },
    ].map((view) => {
      const selected = active === view.key;
      return (
        <TouchableOpacity
          key={view.key}
          style={[styles.viewTab, selected && styles.viewTabActive]}
          onPress={() => onChange(view.key)}
          activeOpacity={0.75}
        >
          <Text style={[styles.viewTabText, selected && styles.viewTabTextActive]}>{view.label}</Text>
        </TouchableOpacity>
      );
    })}
  </View>
);

const NavRow: React.FC<any> = ({ title, sub, onPrev, onNext }) => (
  <View style={styles.navRow}>
    <TouchableOpacity style={styles.navButton} onPress={onPrev} activeOpacity={0.75}>
      <Icon name="ri-arrow-left-s-line" size={22} color="#C9D1D9" />
    </TouchableOpacity>
    <View style={styles.navTitleWrap}>
      <Text style={styles.navTitle}>{title}</Text>
      {sub ? <Text style={styles.navSub}>{sub}</Text> : null}
    </View>
    <TouchableOpacity style={styles.navButton} onPress={onNext} activeOpacity={0.75}>
      <Icon name="ri-arrow-right-s-line" size={22} color="#C9D1D9" />
    </TouchableOpacity>
  </View>
);

const MiniButton: React.FC<any> = ({ label, variant = 'default', onPress }) => (
  <TouchableOpacity
    style={[styles.miniButton, variant === 'primary' && styles.miniButtonPrimary, variant === 'ghost' && styles.miniButtonGhost]}
    onPress={onPress}
    activeOpacity={0.75}
  >
    <Text style={[styles.miniButtonText, variant === 'primary' && styles.miniButtonTextPrimary]}>{getLiteral(label)}</Text>
  </TouchableOpacity>
);

const ActionBar: React.FC<any> = ({ summary, buttons, onClear, context }) => (
  <View style={styles.actionBar}>
    <Text style={[styles.actionText, !summary && styles.actionTextMuted]} numberOfLines={2}>
      {summary || 'No selection'}
    </Text>
    {summary ? (
      <View style={styles.actionButtons}>
        {(Array.isArray(buttons) ? buttons : []).map((button: any, index: number) => (
          <MiniButton
            key={`custom_${index}`}
            label={button.label}
            variant={button.variant}
            onPress={() => button.onCustomClick?.(context)}
          />
        ))}
        <MiniButton label="Clear" variant="ghost" onPress={onClear} />
      </View>
    ) : null}
  </View>
);

const EventPill: React.FC<any> = ({ event, compact, onPress }) => {
  const color = getLiteral(event?.color, '#58A6FF');
  const time = eventTime(event);
  const title = getLiteral(event?.title || event?.label || 'Event');
  return (
    <TouchableOpacity
      style={[styles.eventPill, compact && styles.eventPillCompact, { borderLeftColor: color }]}
      onPress={onPress}
      activeOpacity={onPress ? 0.75 : 1}
    >
      <Text style={[styles.eventPillText, compact && styles.eventPillTextCompact]} numberOfLines={1}>
        {time ? `${time} ` : ''}{title}
      </Text>
    </TouchableOpacity>
  );
};

const MonthView: React.FC<any> = ({
  curDate,
  evByDate,
  selDates,
  onPrev,
  onNext,
  onDayClick,
  onViewDay,
  onClear,
  customButtons,
  onEventClick,
}) => {
  const first = new Date(curDate.getFullYear(), curDate.getMonth(), 1);
  const start = startOfMondayWeek(first);
  const dates = Array.from({ length: 42 }, (_unused, index) => addDays(start, index));
  const selected = new Set(selDates);
  const selectedDay = selDates[0] || '';
  const title = `${MONTH_LONG[curDate.getMonth()]} ${curDate.getFullYear()}`;

  return (
    <View style={styles.viewBody}>
      <NavRow title={title} sub="Tap a day to select it" onPrev={onPrev} onNext={onNext} />
      <ActionBar
        summary={selectedDay ? `Selected: ${fmtDate(selectedDay)}` : ''}
        buttons={[{ label: 'View day', onCustomClick: () => onViewDay(selectedDay) }, ...customButtons]}
        context={{ date: selectedDay }}
        onClear={onClear}
      />
      <View style={styles.weekHeader}>
        {DAY_SHORT.map((day) => <Text key={day} style={styles.weekHeaderText}>{day}</Text>)}
      </View>
      <View style={styles.monthGrid}>
        {dates.map((date) => {
          const key = dateKey(date);
          const inMonth = sameMonth(date, curDate);
          const isToday = key === TODAY;
          const isSelected = selected.has(key);
          const events = evByDate[key] || [];
          return (
            <TouchableOpacity
              key={key}
              style={[
                styles.monthCell,
                !inMonth && styles.monthCellMuted,
                isSelected && styles.monthCellSelected,
              ]}
              onPress={() => onDayClick(key)}
              activeOpacity={0.78}
            >
              <View style={[styles.dayBadge, isToday && styles.dayBadgeToday, isSelected && styles.dayBadgeSelected]}>
                <Text style={[styles.dayBadgeText, isSelected && styles.dayBadgeTextSelected]}>{date.getDate()}</Text>
              </View>
              {events.slice(0, 2).map((event: any, index: number) => (
                <EventPill
                  key={`month_event_${index}`}
                  event={event}
                  compact
                  onPress={onEventClick ? () => onEventClick(event) : undefined}
                />
              ))}
              {events.length > 2 ? <Text style={styles.moreText}>+{events.length - 2}</Text> : null}
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
};

const WeekView: React.FC<any> = ({
  curDate,
  evByDate,
  selSlots,
  onPrev,
  onNext,
  onSlotClick,
  onViewDay,
  onClear,
  customButtons,
  onEventClick,
  timeSlots,
}) => {
  const monday = startOfMondayWeek(curDate);
  const days = Array.from({ length: 7 }, (_unused, index) => addDays(monday, index));
  const last = addDays(monday, 6);
  const title = monday.getMonth() === last.getMonth()
    ? `${MONTH_SHORT[monday.getMonth()]} ${monday.getDate()} - ${last.getDate()}, ${last.getFullYear()}`
    : `${MONTH_SHORT[monday.getMonth()]} ${monday.getDate()} - ${MONTH_SHORT[last.getMonth()]} ${last.getDate()}, ${last.getFullYear()}`;
  const selectedDate = selSlots[0]?.date || '';
  const selectedTimes = selSlots.map((slot: any) => slot.time).join(', ');
  const isSelected = (date: string, time: string) => selSlots.some((slot: any) => slot.date === date && slot.time === time);

  return (
    <View style={styles.viewBody}>
      <NavRow title={title} sub="Tap slots to select them" onPrev={onPrev} onNext={onNext} />
      <ActionBar
        summary={selSlots.length ? `${selSlots.length} slot${selSlots.length > 1 ? 's' : ''} on ${fmtDate(selectedDate)}: ${selectedTimes}` : ''}
        buttons={customButtons}
        context={{ date: selectedDate, time: selSlots[0]?.time || '', slots: selSlots }}
        onClear={onClear}
      />
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <View>
          <View style={styles.weekDaysRow}>
            <View style={styles.timeColumnHeader} />
            {days.map((day) => {
              const key = dateKey(day);
              return (
                <TouchableOpacity key={key} style={styles.weekDayHead} onPress={() => onViewDay(key)} activeOpacity={0.75}>
                  <Text style={[styles.weekDayName, key === TODAY && styles.todayText]}>{DAY_SHORT[(day.getDay() + 6) % 7]}</Text>
                  <Text style={[styles.weekDayNumber, key === TODAY && styles.todayText]}>{day.getDate()}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          {timeSlots.map((slot: string) => (
            <View key={slot} style={styles.weekSlotRow}>
              <Text style={styles.timeLabel}>{slot}</Text>
              {days.map((day) => {
                const key = dateKey(day);
                const events = (evByDate[key] || []).filter((event: any) => eventTime(event).startsWith(slot.slice(0, 2)));
                const active = isSelected(key, slot);
                return (
                  <TouchableOpacity
                    key={`${key}_${slot}`}
                    style={[styles.weekSlotCell, active && styles.slotSelected]}
                    onPress={() => onSlotClick(key, slot)}
                    activeOpacity={0.75}
                  >
                    {events[0] ? (
                      <EventPill
                        event={events[0]}
                        compact
                        onPress={onEventClick ? () => onEventClick(events[0]) : undefined}
                      />
                    ) : null}
                    {events.length > 1 ? <Text style={styles.moreText}>+{events.length - 1}</Text> : null}
                  </TouchableOpacity>
                );
              })}
            </View>
          ))}
        </View>
      </ScrollView>
    </View>
  );
};

const DayView: React.FC<any> = ({
  curDate,
  evByDate,
  selSlots,
  onPrev,
  onNext,
  onSlotClick,
  onClear,
  customButtons,
  onEventClick,
  dayTimeSlots,
}) => {
  const key = dateKey(curDate);
  const events = evByDate[key] || [];
  const selected = new Set(selSlots);
  const title = `${DAY_LONG[(curDate.getDay() + 6) % 7]}, ${MONTH_LONG[curDate.getMonth()]} ${curDate.getDate()}`;

  return (
    <View style={styles.viewBody}>
      <NavRow title={title} sub="Tap slots to select them" onPrev={onPrev} onNext={onNext} />
      <ActionBar
        summary={selSlots.length ? `${selSlots.length} slot${selSlots.length > 1 ? 's' : ''} selected: ${selSlots.join(', ')}` : ''}
        buttons={customButtons}
        context={{ date: key, time: selSlots[0] || '', slots: selSlots }}
        onClear={onClear}
      />
      <View style={styles.dayTimeline}>
        {dayTimeSlots.map((slot: string) => {
          const slotEvents = events.filter((event: any) => {
            const time = eventTime(event);
            return slot.endsWith(':00') ? time.startsWith(slot.slice(0, 2)) : time >= slot && time < `${slot.slice(0, 3)}59`;
          });
          const active = selected.has(slot);
          return (
            <TouchableOpacity
              key={slot}
              style={[styles.daySlot, active && styles.slotSelected]}
              onPress={() => onSlotClick(slot)}
              activeOpacity={0.75}
            >
              <Text style={styles.daySlotTime}>{slot.endsWith(':00') ? slot : ''}</Text>
              <View style={styles.daySlotContent}>
                {slotEvents.map((event: any, index: number) => (
                  <EventPill
                    key={`day_event_${slot}_${index}`}
                    event={event}
                    onPress={onEventClick ? () => onEventClick(event) : undefined}
                  />
                ))}
              </View>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
};

const DatePickerFallback: React.FC<any> = ({
  id,
  label,
  value,
  action,
  onAction,
  setInput,
  style,
  syncInitialInput = true,
}) => {
  const initial = React.useMemo(() => safeDate(value) || new Date(), [value]);
  const [cursor, setCursor] = React.useState(new Date(initial.getFullYear(), initial.getMonth(), 1));
  const [selected, setSelected] = React.useState(dateKey(initial));

  React.useEffect(() => {
    const next = dateKey(initial);
    setSelected(next);
    setCursor(new Date(initial.getFullYear(), initial.getMonth(), 1));
    if (syncInitialInput) setInput?.(id, next);
  }, [id, initial, setInput, syncInitialInput]);

  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const start = startOfMondayWeek(first);
  const days = Array.from({ length: 42 }, (_unused, index) => addDays(start, index));

  const chooseDay = (day: Date) => {
    const next = dateKey(day);
    setSelected(next);
    setInput?.(id, next);
    emitActionSpec(action, onAction, { [id]: next, value: next });
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? <Text style={styles.label}>{getLiteral(label)}</Text> : null}
      <NavRow
        title={`${MONTH_LONG[cursor.getMonth()]} ${cursor.getFullYear()}`}
        onPrev={() => setCursor((prev) => addMonths(prev, -1))}
        onNext={() => setCursor((prev) => addMonths(prev, 1))}
      />
      <View style={styles.weekHeader}>
        {DAY_SHORT.map((day) => <Text key={day} style={styles.weekHeaderText}>{day}</Text>)}
      </View>
      <View style={styles.datePickerGrid}>
        {days.map((day) => {
          const key = dateKey(day);
          const active = selected === key;
          return (
            <TouchableOpacity
              key={key}
              style={[styles.datePickerCell, !sameMonth(day, cursor) && styles.monthCellMuted, active && styles.dayBadgeSelected]}
              onPress={() => chooseDay(day)}
              activeOpacity={0.75}
            >
              <Text style={[styles.dayBadgeText, active && styles.dayBadgeTextSelected]}>{day.getDate()}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
};

export const Calendar: React.FC<any> = ({
  id,
  label,
  value,
  events: eventsProp,
  view: viewProp,
  current_date,
  selected_dates,
  selected_slots,
  buttons: buttonsProp,
  on_event_click: onEventClickProp,
  time_from,
  time_to,
  action,
  onAction,
  setInput,
  style,
  syncInitialInput = true,
}) => {
  const isScheduler = (
    eventsProp !== undefined ||
    viewProp !== undefined ||
    current_date !== undefined ||
    selected_dates !== undefined ||
    selected_slots !== undefined ||
    buttonsProp !== undefined ||
    onEventClickProp !== undefined
  );

  if (!isScheduler) {
    return (
      <DatePickerFallback
        id={id}
        label={label}
        value={value}
        action={action}
        onAction={onAction}
        setInput={setInput}
        style={style}
        syncInitialInput={syncInitialInput}
      />
    );
  }

  const initialDate = safeDate(current_date) || safeDate(value) || new Date();
  const [activeView, setActiveView] = React.useState<'month' | 'week' | 'day'>(() => normalizeView(viewProp));
  const [curDate, setCurDate] = React.useState<Date>(initialDate);
  const [selDates, setSelDates] = React.useState<string[]>(() => (
    Array.isArray(selected_dates) ? selected_dates.map((entry: any) => getLiteral(entry)).filter(Boolean) : []
  ));
  const [weekSlots, setWeekSlots] = React.useState<Array<{ date: string; time: string }>>(() => (
    Array.isArray(selected_slots) ? selected_slots.filter((slot: any) => slot && typeof slot === 'object' && slot.date) : []
  ));
  const [daySlots, setDaySlots] = React.useState<string[]>(() => (
    Array.isArray(selected_slots) ? selected_slots.filter((slot: any) => typeof slot === 'string') : []
  ));

  const viewValue = normalizeView(viewProp);
  const currentDateValue = getLiteral(current_date);
  const selectedDatesSignature = JSON.stringify(Array.isArray(selected_dates) ? selected_dates.map((entry: any) => getLiteral(entry)).filter(Boolean) : []);
  const selectedSlotsSignature = JSON.stringify(Array.isArray(selected_slots) ? selected_slots : []);

  React.useEffect(() => {
    setActiveView(viewValue);
  }, [viewValue]);

  React.useEffect(() => {
    const next = safeDate(currentDateValue);
    if (next) setCurDate(next);
  }, [currentDateValue]);

  React.useEffect(() => {
    setSelDates(Array.isArray(selected_dates) ? selected_dates.map((entry: any) => getLiteral(entry)).filter(Boolean) : []);
  }, [selectedDatesSignature]);

  React.useEffect(() => {
    const raw = Array.isArray(selected_slots) ? selected_slots : [];
    setWeekSlots(raw.filter((slot: any) => slot && typeof slot === 'object' && slot.date));
    setDaySlots(raw.filter((slot: any) => typeof slot === 'string'));
  }, [selectedSlotsSignature]);

  const { from, to } = timeRange(time_from, time_to);
  const timeSlots = React.useMemo(() => buildHourSlots(from, to), [from, to]);
  const dayTimeSlots = React.useMemo(() => buildHalfHourSlots(from, to), [from, to]);
  const evByDate = React.useMemo(() => groupByDate(eventsProp || []), [eventsProp]);

  const customButtons = React.useMemo(() => {
    if (!Array.isArray(buttonsProp)) return [];
    return buttonsProp.map((button: any) => ({
      label: getLiteral(button?.label),
      variant: button?.variant || 'default',
      onCustomClick: (context: Record<string, any>) => {
        if (button?.action) emitActionSpec(button.action, onAction, context);
      },
    }));
  }, [buttonsProp, onAction]);

  const emitCalendarAction = (payload: Record<string, any>) => {
    emitActionSpec(action, onAction, payload);
  };

  const onEventClick = onEventClickProp
    ? (event: any) => emitActionSpec(onEventClickProp, onAction, {
        event,
        date: eventDate(event),
        time: eventTime(event),
        title: getLiteral(event?.title || event?.label),
      })
    : null;

  const nav = (delta: number) => {
    const next = activeView === 'month'
      ? addMonths(curDate, delta)
      : activeView === 'week'
        ? addWeeks(curDate, delta)
        : addDays(curDate, delta);
    setCurDate(next);
    emitCalendarAction({ intent: 'navigate', view: activeView, direction: delta, date: dateKey(next) });
  };

  const switchView = (nextView: 'month' | 'week' | 'day', dateOverride?: string) => {
    const nextDate = dateOverride ? safeDate(dateOverride) : null;
    setActiveView(nextView);
    if (nextDate) setCurDate(nextDate);
    emitCalendarAction({ intent: 'view_change', view: nextView, ...(dateOverride ? { date: dateOverride } : {}) });
  };

  const onDayClick = (day: string) => {
    setSelDates([day]);
    emitCalendarAction({ intent: 'day_click', view: 'month', date: day });
  };

  const onWeekSlot = (date: string, time: string) => {
    setWeekSlots((prev) => {
      const sameDay = prev[0]?.date === date;
      const base = sameDay || prev.length === 0 ? prev : [];
      const exists = base.some((slot) => slot.date === date && slot.time === time);
      return exists ? base.filter((slot) => !(slot.date === date && slot.time === time)) : [...base, { date, time }];
    });
    emitCalendarAction({ intent: 'slot_click', view: 'week', date, time });
  };

  const onDaySlot = (time: string) => {
    const day = dateKey(curDate);
    setDaySlots((prev) => prev.includes(time) ? prev.filter((slot) => slot !== time) : [...prev, time]);
    emitCalendarAction({ intent: 'slot_click', view: 'day', date: day, time });
  };

  const onClear = () => {
    if (activeView === 'month') setSelDates([]);
    else if (activeView === 'week') setWeekSlots([]);
    else setDaySlots([]);
  };

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? <Text style={styles.label}>{getLiteral(label)}</Text> : null}
      <ViewSwitch active={activeView} onChange={(next: 'month' | 'week' | 'day') => switchView(next)} />
      {activeView === 'month' ? (
        <MonthView
          curDate={curDate}
          evByDate={evByDate}
          selDates={selDates}
          onPrev={() => nav(-1)}
          onNext={() => nav(1)}
          onDayClick={onDayClick}
          onViewDay={(day: string) => day && switchView('day', day)}
          onClear={onClear}
          customButtons={customButtons}
          onEventClick={onEventClick}
        />
      ) : null}
      {activeView === 'week' ? (
        <WeekView
          curDate={curDate}
          evByDate={evByDate}
          selSlots={weekSlots}
          onPrev={() => nav(-1)}
          onNext={() => nav(1)}
          onSlotClick={onWeekSlot}
          onViewDay={(day: string) => switchView('day', day)}
          onClear={onClear}
          customButtons={customButtons}
          onEventClick={onEventClick}
          timeSlots={timeSlots}
        />
      ) : null}
      {activeView === 'day' ? (
        <DayView
          curDate={curDate}
          evByDate={evByDate}
          selSlots={daySlots}
          onPrev={() => nav(-1)}
          onNext={() => nav(1)}
          onSlotClick={onDaySlot}
          onClear={onClear}
          customButtons={customButtons}
          onEventClick={onEventClick}
          dayTimeSlots={dayTimeSlots}
        />
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    marginVertical: 6,
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    padding: 10,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    color: '#8B949E',
    marginBottom: 8,
  },
  viewSwitch: {
    flexDirection: 'row',
    alignSelf: 'flex-start',
    borderRadius: 8,
    padding: 3,
    backgroundColor: '#0D1117',
    borderWidth: 1,
    borderColor: '#30363D',
    marginBottom: 12,
  },
  viewTab: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 6,
  },
  viewTabActive: {
    backgroundColor: '#30363D',
  },
  viewTabText: {
    color: '#8B949E',
    fontSize: 13,
    fontWeight: '700',
  },
  viewTabTextActive: {
    color: '#E6EDF3',
  },
  viewBody: {
    gap: 10,
  },
  navRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  navButton: {
    width: 34,
    height: 34,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#21262D',
  },
  navTitleWrap: {
    flex: 1,
    minWidth: 0,
  },
  navTitle: {
    color: '#E6EDF3',
    fontSize: 15,
    fontWeight: '800',
  },
  navSub: {
    color: '#6E7681',
    fontSize: 11,
    marginTop: 2,
  },
  actionBar: {
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#0D1117',
    borderRadius: 8,
    padding: 9,
    gap: 8,
  },
  actionText: {
    color: '#C9D1D9',
    fontSize: 12,
    fontWeight: '600',
  },
  actionTextMuted: {
    color: '#6E7681',
  },
  actionButtons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  miniButton: {
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#21262D',
    borderRadius: 6,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  miniButtonPrimary: {
    backgroundColor: '#238636',
    borderColor: '#238636',
  },
  miniButtonGhost: {
    backgroundColor: 'transparent',
    borderColor: 'transparent',
  },
  miniButtonText: {
    color: '#C9D1D9',
    fontSize: 12,
    fontWeight: '700',
  },
  miniButtonTextPrimary: {
    color: '#FFFFFF',
  },
  weekHeader: {
    flexDirection: 'row',
  },
  weekHeaderText: {
    width: `${100 / 7}%`,
    color: '#8B949E',
    fontSize: 10,
    fontWeight: '800',
    textAlign: 'center',
    textTransform: 'uppercase',
    paddingVertical: 5,
  },
  monthGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderColor: '#30363D',
  },
  monthCell: {
    width: `${100 / 7}%`,
    minHeight: 74,
    borderRightWidth: 1,
    borderBottomWidth: 1,
    borderColor: '#30363D',
    padding: 3,
    backgroundColor: '#161B22',
  },
  monthCellMuted: {
    opacity: 0.35,
  },
  monthCellSelected: {
    backgroundColor: '#1F2A44',
  },
  dayBadge: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
  },
  dayBadgeToday: {
    borderWidth: 1,
    borderColor: '#58A6FF',
  },
  dayBadgeSelected: {
    backgroundColor: '#58A6FF',
  },
  dayBadgeText: {
    color: '#C9D1D9',
    fontSize: 11,
    fontWeight: '700',
  },
  dayBadgeTextSelected: {
    color: '#0D1117',
  },
  eventPill: {
    borderLeftWidth: 3,
    backgroundColor: '#0D1117',
    borderRadius: 6,
    paddingHorizontal: 7,
    paddingVertical: 6,
    marginVertical: 3,
  },
  eventPillCompact: {
    borderRadius: 4,
    paddingHorizontal: 3,
    paddingVertical: 2,
    marginVertical: 1,
  },
  eventPillText: {
    color: '#C9D1D9',
    fontSize: 12,
    fontWeight: '700',
  },
  eventPillTextCompact: {
    fontSize: 9,
  },
  moreText: {
    color: '#8B949E',
    fontSize: 10,
    fontWeight: '700',
    marginTop: 1,
  },
  weekDaysRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  timeColumnHeader: {
    width: 54,
  },
  weekDayHead: {
    width: 86,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderColor: '#30363D',
    paddingVertical: 7,
  },
  weekDayName: {
    color: '#8B949E',
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  weekDayNumber: {
    color: '#C9D1D9',
    fontSize: 14,
    fontWeight: '800',
    marginTop: 2,
  },
  todayText: {
    color: '#58A6FF',
  },
  weekSlotRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  timeLabel: {
    width: 54,
    color: '#6E7681',
    fontSize: 10,
    textAlign: 'right',
    paddingRight: 8,
    paddingTop: 10,
    borderTopWidth: 1,
    borderColor: '#30363D',
  },
  weekSlotCell: {
    width: 86,
    minHeight: 44,
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderColor: '#30363D',
    padding: 2,
  },
  slotSelected: {
    backgroundColor: '#1F2A44',
  },
  dayTimeline: {
    borderTopWidth: 1,
    borderColor: '#30363D',
  },
  daySlot: {
    flexDirection: 'row',
    minHeight: 50,
    borderBottomWidth: 1,
    borderColor: '#30363D',
  },
  daySlotTime: {
    width: 54,
    color: '#6E7681',
    fontSize: 11,
    textAlign: 'right',
    paddingTop: 7,
    paddingRight: 8,
  },
  daySlotContent: {
    flex: 1,
    paddingVertical: 3,
  },
  datePickerGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  datePickerCell: {
    width: `${100 / 7}%`,
    aspectRatio: 1,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
