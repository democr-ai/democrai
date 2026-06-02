import React from 'react';
import {
  format, startOfWeek, addDays, addMonths, subMonths,
  addWeeks, subWeeks, isSameMonth, parseISO, isValid,
} from 'date-fns';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, parseActionSpec, requestActionConfirm } from '@/renderers/shared';
import { CALENDAR_THEME } from '@/utils/dataTheme';

// ─── constants ────────────────────────────────────────────────────────────────

const TODAY = format(new Date(), 'yyyy-MM-dd');
const C = CALENDAR_THEME;
const mixWithTransparent = (color: string, alphaPercent: number): string =>
  `color-mix(in oklab, ${color} ${Math.max(0, Math.min(100, alphaPercent))}%, transparent)`;

function buildTimeSlots(from: number, to: number): string[] {
  const slots: string[] = [];
  for (let h = from; h < to; h++) slots.push(`${String(h).padStart(2,'0')}:00`);
  return slots;
}

function buildDayTimeSlots(from: number, to: number): string[] {
  const slots: string[] = [];
  for (let h = from; h < to; h++) {
    slots.push(`${String(h).padStart(2,'0')}:00`);
    slots.push(`${String(h).padStart(2,'0')}:30`);
  }
  return slots;
}

function eventToSlot(time: string): string {
  try {
    const h = time.slice(0, 2);
    const m = parseInt(time.slice(3, 5), 10);
    return `${h}:${m >= 30 ? '30' : '00'}`;
  } catch { return time.slice(0, 5); }
}

type EvEntry = { ev: any; si: number; span: number; col: number };

function computeEvLayout(evs: any[], slotIdx: Record<string, number>): EvEntry[] {
  const colEnds: Record<number, number> = {};
  const result: EvEntry[] = [];
  const nSlots = Object.keys(slotIdx).length;
  const sorted = [...evs].sort((a, b) => {
    return (slotIdx[eventToSlot(String(a.time || ''))] ?? 0) -
           (slotIdx[eventToSlot(String(b.time || ''))] ?? 0);
  });
  for (const ev of sorted) {
    const slot = eventToSlot(String(ev.time || ''));
    const si   = slotIdx[slot] ?? 0;
    const dur  = Math.max(30, parseInt(String(ev.duration || '30'), 10) || 30);
    const span = Math.min(Math.max(1, Math.ceil(dur / 30)), Math.max(1, nSlots - si));
    let col = 0;
    while ((colEnds[col] ?? 0) > si) col++;
    colEnds[col] = si + span;
    result.push({ ev, si, span, col });
  }
  return result;
}

const DAY_NAMES  = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
const MONTH_LONG = ['January','February','March','April','May','June','July','August','September','October','November','December'];

// ─── tiny helpers ─────────────────────────────────────────────────────────────

function safeDate(str: string | undefined | null): Date | null {
  if (!str) return null;
  try { const d = parseISO(str); return isValid(d) ? d : null; } catch { return null; }
}

function fmtDate(iso: string): string {
  try {
    const p = iso.split('-');
    return `${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+p[1]-1]} ${+p[2]}`;
  } catch { return iso; }
}

function groupByDate(events: any[]): Record<string, any[]> {
  const m: Record<string, any[]> = {};
  for (const ev of (events || [])) {
    const d = ev.date || (typeof ev.start === 'string' ? ev.start.slice(0,10) : '');
    if (d) (m[d] ??= []).push(ev);
  }
  return m;
}

// ─── shared style tokens ──────────────────────────────────────────────────────

const S = {
  navBtn: {
    background: 'none', border: 'none', color: C.textNav,
    fontSize: 18, cursor: 'pointer', padding: '4px 10px', lineHeight: 1,
  } as React.CSSProperties,
  navTitle: { fontSize: 16, fontWeight: 700, color: C.textTitle } as React.CSSProperties,
  navSub:   { fontSize: 12, color: C.textSub } as React.CSSProperties,
  timeLbl:  { fontSize: 11, color: C.textSub, textAlign: 'right' as const, padding: '4px 8px 4px 0', minWidth: 56, width: 56, flexShrink: 0 },
  abarWrap: { padding: '8px 14px', background: C.actionbarBg, borderRadius: 8, border: `1px solid ${C.actionbarBorder}`, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' as const },
  abarLbl:  { fontSize: 13, color: C.textNav } as React.CSSProperties,
};

// ─── mini button (mirrors app Button variants) ────────────────────────────────

const Btn: React.FC<{ label: string; variant?: 'primary'|'default'|'ghost'; small?: boolean; style?: React.CSSProperties; onClick: () => void }> =
  ({ label, variant = 'default', small, style, onClick }) => {
    const base: React.CSSProperties = {
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      borderRadius: 6, cursor: 'pointer', fontWeight: 500, transition: 'opacity .15s',
      fontSize: small ? 12 : 13,
      padding: small ? '3px 10px' : '5px 14px',
      border: variant === 'ghost' ? 'none' : '1px solid',
      background: variant === 'primary' ? C.selectedBorder : variant === 'ghost' ? 'transparent' : C.actionbarBg,
      borderColor: variant === 'primary' ? C.selectedBorder : variant === 'ghost' ? 'transparent' : C.actionbarBorder,
      color: variant === 'primary' ? C.textTitle : variant === 'ghost' ? C.textNav : C.textTitle,
      ...style,
    };
    return <button style={base} onClick={onClick}>{label}</button>;
  };

// ─── nav row ──────────────────────────────────────────────────────────────────

const NavRow: React.FC<{ title: string; sub?: string; onPrev: () => void; onNext: () => void }> =
  ({ title, sub, onPrev, onNext }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <button style={S.navBtn} onClick={onPrev}>‹</button>
      <div style={{ flex: 1 }}>
        <div style={S.navTitle}>{title}</div>
        {sub && <div style={S.navSub}>{sub}</div>}
      </div>
      <button style={S.navBtn} onClick={onNext}>›</button>
    </div>
  );

// ─── month view ───────────────────────────────────────────────────────────────

function MonthView({ curDate, evByDate, selDates, onPrev, onNext, onDayClick, onViewDay, onClear, customButtons, onEventClick }: any) {
  const year = curDate.getFullYear(), month = curDate.getMonth();
  const first = new Date(year, month, 1);
  const start = startOfWeek(first, { weekStartsOn: 1 });
  const weeks: Date[][] = Array.from({ length: 6 }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => addDays(start, w*7+d)));
  const selSet: Set<string> = new Set(selDates);
  const selDay = selDates[0] || null;
  const monthLabel = MONTH_LONG[month];
  const title = `${monthLabel} ${year}`;
  const sub = 'Click a day to select it';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <NavRow title={title} sub={sub} onPrev={onPrev} onNext={onNext} />

      {/* action bar — always visible */}
      <div style={S.abarWrap}>
        {selDay ? (
          <>
            <span style={S.abarLbl}>Selected: {fmtDate(selDay)}</span>
            <Btn label="View day" variant="default" small onClick={() => onViewDay(selDay)} />
            {(customButtons || []).map((btn: any, i: number) => (
              <Btn key={i} label={btn.label} variant={btn.variant || 'default'} small
                onClick={() => btn.onCustomClick({ date: selDay })} />
            ))}
            <Btn label="Clear selection" variant="ghost" small onClick={onClear} />
          </>
        ) : (
          <span style={{ ...S.abarLbl, color: C.actionbarBorder, fontSize: 12 }}>No selection</span>
        )}
      </div>

      {/* grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 2 }}>
        {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d => (
          <div key={d} style={{ textAlign: 'center', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', color: C.textHeader, padding: '8px 4px' }}>{d}</div>
        ))}
        {weeks.flat().map((date, i) => {
          const ds    = format(date, 'yyyy-MM-dd');
          const inMon = isSameMonth(date, curDate);
          const isToday = ds === TODAY;
          const isSel   = selSet.has(ds);
          const evs     = evByDate[ds] || [];
          const border  = isSel ? `2px solid ${C.selectedBorder}` : `1px solid ${C.border}`;
          const bg      = isSel ? C.selectedBg : C.bg;
          const alpha   = inMon ? 1 : 0.4;

          // day number button style
          let dayBtnStyle: React.CSSProperties = { width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, cursor: 'pointer', border: 'none', marginBottom: 2, flexShrink: 0 };
          if (isSel)        dayBtnStyle = { ...dayBtnStyle, background: C.selectedBorder, color: C.textTitle, fontWeight: 700 };
          else if (isToday) dayBtnStyle = { ...dayBtnStyle, background: 'transparent', color: C.selectedBorder, fontWeight: 800, border: `1px solid ${C.selectedBorder}` };
          else              dayBtnStyle = { ...dayBtnStyle, background: 'transparent', color: C.textNav };

          return (
            <div key={i} onClick={() => onDayClick(ds)} style={{ minHeight: 80, padding: 4, border, background: bg, borderRadius: 4, opacity: alpha, cursor: 'pointer', overflow: 'hidden' }}>
              <div style={dayBtnStyle}>{date.getDate()}</div>
              {evs.slice(0,2).map((ev: any, ei: number) => (
                <div key={ei}
                  onClick={onEventClick ? (e) => { e.stopPropagation(); onEventClick(ev); } : undefined}
                  style={{ fontSize: 10, color: ev.color || C.eventFallback, padding: '1px 3px', margin: '1px 2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: onEventClick ? 'pointer' : 'default' }}>
                  ● {ev.time ? `${ev.time} ` : ''}{ev.title}
                </div>
              ))}
              {evs.length > 2 && <div style={{ fontSize: 10, color: C.textSub, padding: '1px 3px' }}>+{evs.length - 2} more</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── week view ────────────────────────────────────────────────────────────────

function WeekView({ curDate, evByDate, selSlots, onPrev, onNext, onSlotClick, onClear, customButtons, onEventClick, timeSlots, onViewDay }: any) {
  const monday = startOfWeek(curDate, { weekStartsOn: 1 });
  const days   = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const isSlotSel = (ds: string, t: string) =>
    (selSlots as any[]).some((s: any) => s.date === ds && s.time === t);

  const last   = addDays(monday, 6);
  const wkLbl  = monday.getMonth() === last.getMonth()
    ? `${format(monday,'MMM d')} – ${last.getDate()}, ${last.getFullYear()}`
    : `${format(monday,'MMM d')} – ${format(last,'MMM d')}, ${last.getFullYear()}`;
  const sub    = 'Click a slot to select it · same-day multi-select';

  const slots: any[] = selSlots;
  const selDate = slots[0]?.date || '';
  const selTimes = slots.map((s: any) => s.time).join(', ');
  const count = slots.length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <div style={{ marginBottom: 10 }}>
        <NavRow title={wkLbl} sub={sub} onPrev={onPrev} onNext={onNext} />
      </div>

      {/* action bar — always visible */}
      <div style={{ ...S.abarWrap, marginBottom: 8 }}>
        {count > 0 ? (
          <>
            <span style={S.abarLbl}>{count} slot{count > 1 ? 's' : ''} on {fmtDate(selDate)} · {selTimes}</span>
            {(customButtons || []).map((btn: any, i: number) => (
              <Btn key={i} label={btn.label} variant={btn.variant || 'default'} small
                onClick={() => btn.onCustomClick({ date: selDate, time: selTimes.split(', ')[0] || '', slots: slots })} />
            ))}
            <Btn label="Clear selection" variant="ghost" small onClick={onClear} />
          </>
        ) : (
          <span style={{ ...S.abarLbl, color: C.actionbarBorder, fontSize: 12 }}>No selection</span>
        )}
      </div>

      {/* column headers */}
      <div style={{ display: 'flex', alignItems: 'stretch' }}>
        <div style={{ ...S.timeLbl }} />
        {days.map(day => {
          const ds = format(day, 'yyyy-MM-dd');
          const c  = ds === TODAY ? C.selectedBorder : C.textNav;
          return (
            <div key={ds} onClick={() => onViewDay && onViewDay(ds)}
              style={{ flex: 1, fontSize: 11, fontWeight: 700, textAlign: 'center', padding: '6px 4px', borderBottom: `1px solid ${C.border}`, color: c, cursor: onViewDay ? 'pointer' : 'default' }}>
              {format(day,'EEE')}<br />{day.getDate()}
            </div>
          );
        })}
      </div>

      {/* slot rows */}
      {(timeSlots as string[]).map(slot => (
        <div key={slot} style={{ display: 'flex', alignItems: 'stretch' }}>
          <div style={{ ...S.timeLbl, lineHeight: '32px', borderTop: `1px solid ${C.border}` }}>{slot}</div>
          {days.map(day => {
            const ds    = format(day, 'yyyy-MM-dd');
            const slEvs = (evByDate[ds] || []).filter((e: any) => String(e.time||'').startsWith(slot.slice(0,2)));
            const isSel = isSlotSel(ds, slot);
            const ev0   = slEvs[0];
            const color = ev0?.color || C.eventFallback;
            const bg    = isSel ? C.slotSelected : slEvs.length ? mixWithTransparent(color, 14) : 'transparent';
            const borderC = isSel ? mixWithTransparent(C.selectedBorder, 26) : C.border;
            const extra = slEvs.length > 1 ? ` +${slEvs.length - 1}` : '';

            return (
              <div
                key={ds}
                onClick={() => onSlotClick(ds, slot)}
                style={{ flex: 1, minHeight: 32, border: `1px solid ${borderC}`, borderLeft: 'none', background: bg, cursor: 'pointer', padding: 2, overflow: 'hidden' }}
              >
                {ev0 && (
                  <div
                    onClick={onEventClick ? (e) => { e.stopPropagation(); onEventClick(ev0); } : undefined}
                    style={{ fontSize: 10, color, padding: '1px 3px', margin: '3px 4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: onEventClick ? 'pointer' : 'default' }}>
                    ● {ev0.title}{extra}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

// ─── day view ─────────────────────────────────────────────────────────────────

const DAY_SLOT_H = 48;  // px per 30-min slot
const DAY_TIME_W = 56;  // px for time label column

function DayView({ curDate, evByDate, selSlots, onPrev, onNext, onSlotClick, onClear, customButtons, onEventClick, dayTimeSlots }: any) {
  const ds      = format(curDate, 'yyyy-MM-dd');
  const evs     = (evByDate[ds] || []) as any[];
  const selSet  = new Set(selSlots as string[]);
  const d       = curDate;
  const dayLbl  = `${DAY_NAMES[d.getDay() === 0 ? 6 : d.getDay()-1]}, ${MONTH_LONG[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  const sub     = 'Click a slot to select it · multi-select';
  const count   = selSlots.length;
  const slots   = dayTimeSlots as string[];

  const slotIdx = React.useMemo(() => {
    const m: Record<string, number> = {};
    slots.forEach((s, i) => { m[s] = i; });
    return m;
  }, [dayTimeSlots]);

  const evLayout = React.useMemo(() => computeEvLayout(evs, slotIdx), [evs, slotIdx]);
  const nCols    = Math.max(1, ...evLayout.map(({ col }) => col + 1));
  const totalH   = slots.length * DAY_SLOT_H;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <NavRow title={dayLbl} sub={sub} onPrev={onPrev} onNext={onNext} />

      {/* action bar — always visible */}
      <div style={S.abarWrap}>
        {count > 0 ? (
          <>
            <span style={S.abarLbl}>{count} slot{count > 1 ? 's' : ''} selected · {(selSlots as string[]).join(', ')}</span>
            {(customButtons || []).map((btn: any, i: number) => (
              <Btn key={i} label={btn.label} variant={btn.variant || 'default'} small
                onClick={() => btn.onCustomClick({ date: ds, time: selSlots[0] || '', slots: selSlots })} />
            ))}
            <Btn label="Clear selection" variant="ghost" small onClick={onClear} />
          </>
        ) : (
          <span style={{ ...S.abarLbl, color: C.actionbarBorder, fontSize: 12 }}>No selection</span>
        )}
      </div>

      {/* grid — absolute positioning for spans + multi-column overlap */}
      <div style={{ position: 'relative', height: totalH }}>

        {/* time labels — clickable to select the slot */}
        {slots.map((slot, i) => (
          <div key={slot} onClick={() => onSlotClick(slot)} style={{
            position: 'absolute', left: 0, top: i * DAY_SLOT_H,
            width: DAY_TIME_W, height: DAY_SLOT_H,
            fontSize: 12, color: C.textSub, boxSizing: 'border-box',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end',
            padding: '4px 8px 0 0',
            cursor: 'pointer', zIndex: 1,
          }}>
            {slot.endsWith(':00') ? slot : ''}
          </div>
        ))}

        {/* slot background cells — clickable for selection */}
        {slots.map((slot, i) => {
          const isSel = selSet.has(slot);
          return (
            <div key={slot} onClick={() => onSlotClick(slot)} style={{
              position: 'absolute', left: DAY_TIME_W, top: i * DAY_SLOT_H,
              right: 0, height: DAY_SLOT_H,
              background: isSel ? C.slotSelected : 'transparent',
              borderTop: `1px solid ${C.border}`,
              cursor: 'pointer', zIndex: 0, boxSizing: 'border-box',
            }} />
          );
        })}

        {/* event blocks — absolutely positioned, z=1 so they sit above slot cells */}
        {evLayout.map(({ ev, si, span, col }, idx) => {
          const isSel = selSet.has(slots[si] ?? '');
          const color = ev.color || C.eventFallback;
          return (
            <div
              key={idx}
              onClick={onEventClick ? (e: React.MouseEvent) => { e.stopPropagation(); onEventClick(ev); } : undefined}
              style={{
                position: 'absolute',
                left: `calc(${DAY_TIME_W}px + ${col} * (100% - ${DAY_TIME_W}px) / ${nCols} + 2px)`,
                top: si * DAY_SLOT_H + 2,
                width: `calc((100% - ${DAY_TIME_W}px) / ${nCols} - 4px)`,
                height: span * DAY_SLOT_H - 4,
                background: mixWithTransparent(color, isSel ? 34 : 14),
                borderLeft: `3px solid ${color}`,
                borderRadius: 4,
                padding: '6px 8px',
                boxSizing: 'border-box',
                overflow: 'hidden',
                cursor: onEventClick ? 'pointer' : 'default',
                zIndex: 1,
              }}
            >
              <div style={{ fontSize: 10, color, fontWeight: 600 }}>{ev.time}</div>
              <div style={{ fontSize: 13, color, fontWeight: 600 }}>{ev.title}</div>
              {ev.description && (
                <div style={{ fontSize: 11, color: mixWithTransparent(color, 60), marginTop: 2 }}>{ev.description}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── view tab bar ─────────────────────────────────────────────────────────────

const VIEWS = [
  { key: 'month', label: 'Month' },
  { key: 'week',  label: 'Week'  },
  { key: 'day',   label: 'Day'   },
] as const;

function ViewTabs({ active, onSwitch }: { active: string; onSwitch: (v: string) => void }) {
  return (
    <div style={{ display: 'flex', borderBottom: `1px solid ${C.border}`, marginBottom: 16 }}>
      {VIEWS.map(v => (
        <button
          key={v.key}
          onClick={() => onSwitch(v.key)}
          style={{
            padding: '8px 18px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
            background: 'transparent', border: 'none', borderRadius: 0,
            borderBottom: active === v.key ? `2px solid ${C.selectedBorder}` : '2px solid transparent',
            color: active === v.key ? C.selectedBorder : C.textHeader,
            transition: 'color .15s, border-color .15s',
          }}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}

// ─── main Calendar component ──────────────────────────────────────────────────

export const Calendar: React.FC<any> = ({
  id,
  events: eventsProp,
  view: viewProp,
  current_date,
  selected_dates,
  selected_slots,
  buttons: buttonsProp,
  on_event_click: onEventClickProp,
  time_from: timeFromProp,
  time_to: timeToProp,
  action, onAction, setInput, style,
}) => {
  const initView  = (getLiteral(viewProp)    || 'month') as 'month'|'week'|'day';
  const initDate  = safeDate(getLiteral(current_date)) ?? new Date();
  const currentDateValue = getLiteral(current_date) || '';
  const viewValue = (getLiteral(viewProp) || 'month') as 'month'|'week'|'day';
  const selectedDatesValue = React.useMemo(
    () => (Array.isArray(selected_dates) ? selected_dates.map(getLiteral).filter(Boolean) : []),
    [selected_dates],
  );
  const selectedDatesSignature = selectedDatesValue.join('\u0001');
  const selectedSlotsValue = React.useMemo(() => {
    if (!Array.isArray(selected_slots)) {
      return { week: [] as {date:string;time:string}[], day: [] as string[] };
    }
    return {
      week: (selected_slots as any[]).filter(s => s && typeof s === 'object' && s.date),
      day: (selected_slots as any[]).filter((s): s is string => typeof s === 'string'),
    };
  }, [selected_slots]);
  const selectedSlotsSignature = JSON.stringify(selectedSlotsValue);

  const [activeView, setActiveView] = React.useState<'month'|'week'|'day'>(initView);
  const [curDate,    setCurDate]    = React.useState<Date>(initDate);
  const [selDates,   setSelDates]   = React.useState<string[]>(() => selectedDatesValue);
  const [weekSlots,  setWeekSlots]  = React.useState<{date:string;time:string}[]>(() => selectedSlotsValue.week);
  const [daySlots,   setDaySlots]   = React.useState<string[]>(() => selectedSlotsValue.day);
  const lastSelectedDatesSignature = React.useRef(selectedDatesSignature);
  const lastSelectedSlotsSignature = React.useRef(selectedSlotsSignature);

  // sync from server propertyUpdates
  React.useEffect(() => { if (viewValue) setActiveView(viewValue); }, [viewValue]);
  React.useEffect(() => { const d = safeDate(currentDateValue); if (d) setCurDate(d); }, [currentDateValue]);
  React.useEffect(() => {
    if (selectedDatesSignature === lastSelectedDatesSignature.current) return;
    lastSelectedDatesSignature.current = selectedDatesSignature;
    setSelDates(selectedDatesValue);
  }, [selectedDatesSignature, selectedDatesValue]);
  React.useEffect(() => {
    if (selectedSlotsSignature === lastSelectedSlotsSignature.current) return;
    lastSelectedSlotsSignature.current = selectedSlotsSignature;
    setWeekSlots(selectedSlotsValue.week);
    setDaySlots(selectedSlotsValue.day);
  }, [selectedSlotsSignature, selectedSlotsValue]);

  const timeFrom = Math.max(0,  parseInt(getLiteral(timeFromProp) ?? '0',  10) || 0);
  const timeTo   = Math.min(24, parseInt(getLiteral(timeToProp)   ?? '24', 10) || 24);
  const timeSlots    = React.useMemo(() => buildTimeSlots(timeFrom, timeTo),    [timeFrom, timeTo]);
  const dayTimeSlots = React.useMemo(() => buildDayTimeSlots(timeFrom, timeTo), [timeFrom, timeTo]);

  const evByDate = React.useMemo(() => groupByDate(eventsProp ?? []), [eventsProp]);

  const emit = async (payload: Record<string, any>) => {
    const parsed = parseActionSpec(action);
    if (!parsed.name) return true;
    if (parsed.confirm && !(await requestActionConfirm(parsed.confirm))) {
      return false;
    }
    const actionWithoutConfirm = action && typeof action === 'object'
      ? { ...action, confirm: undefined }
      : action;
    emitActionSpec(actionWithoutConfirm, onAction, payload);
    return true;
  };

  // on_event_click — fires when an event is clicked, passes full event data
  const onEventClick = React.useMemo(() => {
    if (!onEventClickProp || !onEventClickProp.name) return null;
    return (ev: any) => emitActionSpec(onEventClickProp, onAction, {
      event: ev, date: ev.date || '', time: ev.time || '', title: ev.title || '',
    });
  }, [onEventClickProp, onAction]);

  // custom buttons — each gets its own onCustomClick that fires the button's own action
  const customButtons = React.useMemo(() => {
    if (!Array.isArray(buttonsProp)) return [];
    return buttonsProp.map((btn: any) => ({
      label:   btn.label,
      variant: btn.variant || 'default',
      onCustomClick: (selContext: Record<string, any>) => {
        if (btn.action) emitActionSpec(btn.action, onAction, selContext);
      },
    }));
  }, [buttonsProp, onAction]);

  const nav = async (delta: number) => {
    let nextDate = curDate;
    if (activeView === 'month') nextDate = delta > 0 ? addMonths(curDate, 1) : subMonths(curDate, 1);
    else if (activeView === 'week') nextDate = delta > 0 ? addWeeks(curDate, 1) : subWeeks(curDate, 1);
    else nextDate = addDays(curDate, delta);
    if (!(await emit({ intent: 'navigate', view: activeView, direction: delta, date: format(nextDate, 'yyyy-MM-dd') }))) {
      return;
    }
    setCurDate(nextDate);
  };

  const switchView = async (v: 'month'|'week'|'day', dateOverride?: string) => {
    const nextDate = dateOverride ? safeDate(dateOverride) : null;
    if (!(await emit({
      intent: 'view_change',
      view: v,
      ...(dateOverride ? { date: dateOverride } : {}),
    }))) {
      return;
    }
    setActiveView(v);
    if (nextDate) setCurDate(nextDate);
  };

  const onDayClick = async (ds: string) => {
    if (!(await emit({ intent: 'day_click', view: 'month', date: ds }))) {
      return;
    }
    setSelDates([ds]);
  };

  const onWeekSlot = async (ds: string, time: string) => {
    if (!(await emit({ intent: 'slot_click', view: 'week', date: ds, time }))) {
      return;
    }
    setWeekSlots(prev => {
      const existDay = prev[0]?.date;
      const base     = existDay && existDay !== ds ? [] : prev;
      const idx      = base.findIndex(s => s.date === ds && s.time === time);
      return idx >= 0 ? base.filter((_,i) => i !== idx) : [...base, {date:ds,time}];
    });
  };

  const onDaySlot = async (time: string) => {
    if (!(await emit({ intent: 'slot_click', view: 'day', date: format(curDate, 'yyyy-MM-dd'), time }))) {
      return;
    }
    setDaySlots(prev => prev.includes(time) ? prev.filter(t => t !== time) : [...prev, time]);
  };

  // clear selection — local only
  const onClear = () => {
    if (activeView === 'month') setSelDates([]);
    else if (activeView === 'week') setWeekSlots([]);
    else setDaySlots([]);
  };

  return (
    <div style={{ ...parseStyle(style) }}>
      <ViewTabs active={activeView} onSwitch={v => switchView(v as any)} />
      {activeView === 'month' && (
        <MonthView curDate={curDate} evByDate={evByDate} selDates={selDates}
          onPrev={() => nav(-1)} onNext={() => nav(1)}
          onDayClick={onDayClick}
          onViewDay={(d: string) => switchView('day', d)} onClear={onClear}
          customButtons={customButtons} onEventClick={onEventClick} />
      )}
      {activeView === 'week' && (
        <WeekView curDate={curDate} evByDate={evByDate} selSlots={weekSlots}
          onPrev={() => nav(-1)} onNext={() => nav(1)}
          onSlotClick={onWeekSlot} onClear={onClear}
          customButtons={customButtons} onEventClick={onEventClick}
          timeSlots={timeSlots}
          onViewDay={(d: string) => switchView('day', d)} />
      )}
      {activeView === 'day' && (
        <DayView curDate={curDate} evByDate={evByDate} selSlots={daySlots}
          onPrev={() => nav(-1)} onNext={() => nav(1)}
          onSlotClick={onDaySlot} onClear={onClear}
          customButtons={customButtons} onEventClick={onEventClick}
          dayTimeSlots={dayTimeSlots} />
      )}
    </div>
  );
};

// ─── datepicker fallback ──────────────────────────────────────────────────────

const DatePicker: React.FC<any> = ({ id, value, min_date, max_date, label, action, onAction, setInput, style }) => {
  const [cursor,   setCursor]   = React.useState<Date>(safeDate(getLiteral(value)) ?? new Date());
  const [selected, setSelected] = React.useState<string>(getLiteral(value) || '');

  React.useEffect(() => {
    const v = getLiteral(value);
    setSelected(v || '');
    const d = safeDate(v); if (d) setCursor(d);
  }, [value]);

  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const start = startOfWeek(first, { weekStartsOn: 1 });
  const weeks: Date[][] = Array.from({length:6}, (_,w) => Array.from({length:7}, (_,d) => addDays(start, w*7+d)));
  const minD = getLiteral(min_date), maxD = getLiteral(max_date);

  const pick = (ds: string) => {
    setSelected(ds);
    setInput?.(id, ds);
    emitActionSpec(action, onAction, { [id]: ds, value: ds });
  };

  return (
    <div style={{ display: 'inline-block', background: C.bg, borderRadius: 8, border: `1px solid ${C.border}`, padding: 12, ...parseStyle(style) }}>
      {label && <div style={{ fontSize: 12, color: C.textNav, marginBottom: 6 }}>{getLiteral(label)}</div>}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
        <button style={S.navBtn} onClick={() => setCursor(c => subMonths(c,1))}>‹</button>
        <span style={{ flex:1, textAlign:'center', fontWeight:700, fontSize:14, color:C.textTitle }}>{format(cursor,'MMMM yyyy')}</span>
        <button style={S.navBtn} onClick={() => setCursor(c => addMonths(c,1))}>›</button>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(7, 32px)', gap:2 }}>
        {['Mo','Tu','We','Th','Fr','Sa','Su'].map(d => (
          <div key={d} style={{ textAlign:'center', fontSize:10, color:C.textHeader, padding:'4px 0' }}>{d}</div>
        ))}
        {weeks.flat().map((date, i) => {
          const ds = format(date,'yyyy-MM-dd');
          const inM = isSameMonth(date, cursor);
          const isSel = ds === selected;
          const isToday = ds === TODAY;
          const disabled = (minD && ds < minD) || (maxD && ds > maxD);
          return (
            <div key={i} onClick={() => !disabled && pick(ds)} style={{
              width:32, height:32, display:'flex', alignItems:'center', justifyContent:'center',
              borderRadius:'50%', fontSize:12, cursor: disabled ? 'default' : 'pointer',
              opacity: (!inM || disabled) ? 0.3 : 1,
              background: isSel ? C.selectedBorder : isToday ? C.slotSelected : 'transparent',
              color: isSel ? C.textTitle : C.textNav, fontWeight: isToday ? 700 : 400,
            }}>{date.getDate()}</div>
          );
        })}
      </div>
    </div>
  );
};
