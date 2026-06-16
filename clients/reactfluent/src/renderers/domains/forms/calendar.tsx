import React from 'react';
import {
  format, startOfWeek, addDays, addMonths, subMonths,
  addWeeks, subWeeks, isSameMonth, parseISO, isValid,
} from 'date-fns';
import { enUS } from 'date-fns/locale';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral, parseActionSpec, requestActionConfirm } from '@/renderers/shared';
import { Badge, Button } from '@/design/system';
import { Pivot, PivotItem } from '@fluentui/react';

const TODAY = format(new Date(), 'yyyy-MM-dd');

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

function safeDate(str: string | undefined | null): Date | null {
  if (!str) return null;
  try { const d = parseISO(str); return isValid(d) ? d : null; } catch { return null; }
}

function fmtDate(iso: string): string {
  try {
    const d = parseISO(iso);
    return format(d, 'd MMM', { locale: enUS });
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

const NavRow: React.FC<{ title: string; sub?: string; onPrev: () => void; onNext: () => void }> =
  ({ title, sub, onPrev, onNext }) => (
    <div className="d-flex align-items-center gap-3 mb-3">
      <Button color="primary" outline size="sm" onClick={onPrev}>
        <i className="ri-arrow-left-s-line" />
      </Button>
      <div className="flex-grow-1">
        <h5 className="m-0 fw-bold">{title}</h5>
        {sub && <p className="m-0 small text-muted">{sub}</p>}
      </div>
      <Button color="primary" outline size="sm" onClick={onNext}>
        <i className="ri-arrow-right-s-line" />
      </Button>
    </div>
  );

function MonthView({ curDate, evByDate, selDates, onPrev, onNext, onDayClick, onViewDay, onClear, customButtons, onEventClick }: any) {
  const year = curDate.getFullYear(), month = curDate.getMonth();
  const first = new Date(year, month, 1);
  const start = startOfWeek(first, { weekStartsOn: 1 });
  const weeks: Date[][] = Array.from({ length: 6 }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => addDays(start, w*7+d)));
  const selSet: Set<string> = new Set(selDates);
  const selDay = selDates[0] || null;
  const monthLabel = format(curDate, 'MMMM', { locale: enUS });

  return (
    <div className="d-flex flex-column gap-2">
      <NavRow title={`${monthLabel} ${year}`} sub="Click a day to select it" onPrev={onPrev} onNext={onNext} />

      <div className="ds-calendar-selection d-flex align-items-center gap-2 p-2 bg-light border mb-2 flex-wrap">
        {selDay ? (
          <>
            <span className="small fw-bold me-2">Selected: {fmtDate(selDay)}</span>
            <Button color="primary" size="xs" onClick={() => onViewDay(selDay)}>View day</Button>
            {(customButtons || []).map((btn: any, i: number) => (
              <Button key={i} color={btn.variant === 'primary' ? 'primary' : 'secondary'} size="xs" outline
                onClick={() => btn.onCustomClick({ date: selDay })}>{btn.label}</Button>
            ))}
            <Button color="link" size="xs" className="ms-auto" onClick={onClear}>Clear</Button>
          </>
        ) : (
          <span className="xsmall text-muted">No selection</span>
        )}
      </div>

      <div className="ds-calendar-month-grid d-grid" style={{ gridTemplateColumns: 'repeat(7, minmax(0, 1fr))' }}>
        {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d => (
          <div key={d} className="ds-calendar-month-head text-center py-2 xsmall fw-bold text-uppercase text-muted">{d}</div>
        ))}
        {weeks.flat().map((date, i) => {
          const ds    = format(date, 'yyyy-MM-dd');
          const inMon = isSameMonth(date, curDate);
          const isToday = ds === TODAY;
          const isSel   = selSet.has(ds);
          const evs     = evByDate[ds] || [];

          return (
            <div key={i} onClick={() => onDayClick(ds)}
              className={`ds-calendar-month-cell p-1 d-flex flex-column gap-1 position-relative ${!inMon ? 'ds-calendar-outside-month' : ''} ${isSel ? 'ds-calendar-selected-cell' : ''}`}
              style={{ cursor: 'pointer' }}>
              <div className={`d-inline-flex align-items-center justify-content-center rounded-circle xsmall fw-bold ${isSel ? 'bg-primary text-white' : isToday ? 'border border-primary text-primary' : ''}`}
                style={{ width: '24px', height: '24px' }}>
                {date.getDate()}
              </div>
              <div className="overflow-hidden">
                {evs.slice(0, 3).map((ev: any, ei: number) => (
                  <div key={ei}
                    onClick={onEventClick ? (e) => { e.stopPropagation(); onEventClick(ev); } : undefined}
                    className="ds-calendar-event text-truncate p-1 mb-1 bg-light border-start border-3"
                    style={{ borderLeftColor: ev.color || '#0066cc' }}>
                    {ev.time && <span className="fw-bold me-1">{ev.time}</span>}
                    {ev.title}
                  </div>
                ))}
                {evs.length > 3 && <div className="ds-calendar-more text-muted text-center">+{evs.length - 3} more</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WeekView({ curDate, evByDate, selSlots, onPrev, onNext, onSlotClick, onClear, customButtons, onEventClick, timeSlots, onViewDay }: any) {
  const monday = startOfWeek(curDate, { weekStartsOn: 1 });
  const days   = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const isSlotSel = (ds: string, t: string) =>
    (selSlots as any[]).some((s: any) => s.date === ds && s.time === t);

  const last   = addDays(monday, 6);
  const wkLbl  = monday.getMonth() === last.getMonth()
    ? `${format(monday,'d')} - ${format(last, 'd MMMM yyyy', { locale: enUS })}`
    : `${format(monday,'d MMM', { locale: enUS })} - ${format(last, 'd MMM yyyy', { locale: enUS })}`;

  const slots: any[] = selSlots;
  const selDate = slots[0]?.date || '';
  const selTimes = slots.map((s: any) => s.time).join(', ');
  const count = slots.length;

  return (
    <div className="d-flex flex-column">
      <NavRow title={wkLbl} sub="Click a slot to select it (same-day multi-selection)" onPrev={onPrev} onNext={onNext} />

      <div className="ds-calendar-selection d-flex align-items-center gap-2 p-2 bg-light border mb-3 flex-wrap">
        {count > 0 ? (
          <>
            <span className="small fw-bold">{count} slots on {fmtDate(selDate)}: {selTimes}</span>
            {(customButtons || []).map((btn: any, i: number) => (
              <Button key={i} color="primary" size="xs" outline
                onClick={() => btn.onCustomClick({ date: selDate, time: selTimes.split(', ')[0] || '', slots: slots })}>{btn.label}</Button>
            ))}
            <Button color="link" size="xs" className="ms-auto" onClick={onClear}>Clear</Button>
          </>
        ) : (
          <span className="xsmall text-muted">No selection</span>
        )}
      </div>

      <div className="ds-calendar-week-wrap table-responsive border">
        <table className="ds-calendar-week-table table table-bordered table-sm m-0 xsmall">
          <thead>
            <tr>
              <th style={{ width: '60px' }}></th>
              {days.map(day => {
                const ds = format(day, 'yyyy-MM-dd');
                const isToday = ds === TODAY;
                return (
                  <th key={ds} className={`text-center py-2 ${isToday ? 'bg-primary-subtle text-primary' : ''}`}
                    onClick={() => onViewDay && onViewDay(ds)} style={{ cursor: 'pointer' }}>
                    <div className="text-uppercase xsmall opacity-75">{format(day,'EEE', { locale: enUS })}</div>
                    <div className="fw-bold fs-6">{day.getDate()}</div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {(timeSlots as string[]).map(slot => (
              <tr key={slot}>
                <td className="text-end pe-2 text-muted py-2">{slot}</td>
                {days.map(day => {
                  const ds    = format(day, 'yyyy-MM-dd');
                  const slEvs = (evByDate[ds] || []).filter((e: any) => String(e.time||'').startsWith(slot.slice(0,2)));
                  const isSel = isSlotSel(ds, slot);
                  const ev0   = slEvs[0];

                  return (
                    <td
                      key={ds}
                      onClick={() => onSlotClick(ds, slot)}
                      className={`ds-calendar-week-cell ${isSel ? 'table-primary' : ''}`}
                      style={{ cursor: 'pointer' }}
                    >
                      {ev0 && (
                        <div
                          onClick={onEventClick ? (e) => { e.stopPropagation(); onEventClick(ev0); } : undefined}
                          className="ds-calendar-event p-1 bg-light border-start border-2 h-100 overflow-hidden"
                          style={{ borderLeftColor: ev0.color || '#0066cc' }}>
                          <span className="text-truncate d-block">{ev0.title}</span>
                          {slEvs.length > 1 && <Badge color="secondary" className="ms-1">+{slEvs.length - 1}</Badge>}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const DAY_SLOT_H = 52;
const DAY_SLOT_MAX_H = 112;

function estimateDayEventHeight(ev: any): number {
  const title = String(ev?.title || '');
  const description = String(ev?.description || '');
  const titleLines = Math.max(1, Math.ceil(title.length / 34));
  const descriptionLines = description ? Math.min(3, Math.ceil(description.length / 42)) : 0;
  return Math.min(DAY_SLOT_MAX_H, 24 + titleLines * 18 + descriptionLines * 15);
}

function DayView({ curDate, evByDate, selSlots, onPrev, onNext, onSlotClick, onClear, customButtons, onEventClick, dayTimeSlots }: any) {
  const ds      = format(curDate, 'yyyy-MM-dd');
  const evs     = (evByDate[ds] || []) as any[];
  const selSet  = new Set(selSlots as string[]);
  const dayLbl  = format(curDate, 'EEEE d MMMM yyyy', { locale: enUS });
  const count   = selSlots.length;
  const slots   = dayTimeSlots as string[];

  const slotIdx = React.useMemo(() => {
    const m: Record<string, number> = {};
    slots.forEach((s, i) => { m[s] = i; });
    return m;
  }, [slots]);

  const evLayout = React.useMemo(() => computeEvLayout(evs, slotIdx), [evs, slotIdx]);
  const nCols    = Math.max(1, ...evLayout.map(({ col }) => col + 1));
  const slotMetrics = React.useMemo(() => {
    const heights = slots.map(() => DAY_SLOT_H);
    evLayout.forEach(({ ev, si, span }) => {
      const needed = estimateDayEventHeight(ev) + 8;
      const current = heights.slice(si, si + span).reduce((sum, h) => sum + h, 0);
      if (needed > current) {
        const extra = Math.ceil((needed - current) / span);
        for (let i = si; i < Math.min(slots.length, si + span); i++) {
          heights[i] = Math.min(DAY_SLOT_MAX_H, heights[i] + extra);
        }
      }
    });
    const offsets: number[] = [];
    let cursor = 0;
    heights.forEach((height) => {
      offsets.push(cursor);
      cursor += height;
    });
    return { heights, offsets, totalHeight: cursor };
  }, [evLayout, slots]);

  return (
    <div className="d-flex flex-column gap-2">
      <NavRow title={dayLbl} sub="Click a slot to select it (multi-selection)" onPrev={onPrev} onNext={onNext} />

      <div className="ds-calendar-selection d-flex align-items-center gap-2 p-2 bg-light border mb-3 flex-wrap">
        {count > 0 ? (
          <>
            <span className="small fw-bold">{count} selected slots: {selSlots.join(', ')}</span>
            {(customButtons || []).map((btn: any, i: number) => (
              <Button key={i} color="primary" size="xs" outline
                onClick={() => btn.onCustomClick({ date: ds, time: selSlots[0] || '', slots: selSlots })}>{btn.label}</Button>
            ))}
            <Button color="link" size="xs" className="ms-auto" onClick={onClear}>Clear</Button>
          </>
        ) : (
          <span className="xsmall text-muted">No selection</span>
        )}
      </div>

      <div className="ds-calendar-day-wrap position-relative border bg-white overflow-auto" style={{ height: '600px' }}>
        <div className="position-relative" style={{ height: slotMetrics.totalHeight }}>
          {slots.map((slot, i) => {
            const isSel = selSet.has(slot);
            return (
              <div key={slot} className="position-absolute w-100 d-flex" 
                style={{ top: slotMetrics.offsets[i], height: slotMetrics.heights[i], borderTop: '1px solid #dee2e6' }}>
                <div className="text-end pe-2 text-muted xsmall py-2 fw-bold" style={{ width: '60px' }}>
                  {slot.endsWith(':00') ? slot : ''}
                </div>
                <div 
                  className={`flex-grow-1 ${isSel ? 'bg-primary-subtle' : ''}`} 
                  onClick={() => onSlotClick(slot)}
                  style={{ cursor: 'pointer' }}
                />
              </div>
            );
          })}

          {evLayout.map(({ ev, si, span, col }, idx) => {
            const color = ev.color || '#0066cc';
            return (
              <div
                key={idx}
                onClick={onEventClick ? (e: React.MouseEvent) => { e.stopPropagation(); onEventClick(ev); } : undefined}
                className="ds-calendar-day-event position-absolute p-2 overflow-hidden border-start border-4"
                style={{
                  left: `calc(60px + ${col} * (100% - 60px) / ${nCols} + 4px)`,
                  top: slotMetrics.offsets[si] + 4,
                  width: `calc((100% - 60px) / ${nCols} - 8px)`,
                  height: slotMetrics.heights.slice(si, si + span).reduce((sum, h) => sum + h, 0) - 8,
                  backgroundColor: `${color}1A`,
                  borderLeftColor: color,
                  cursor: 'pointer',
                  zIndex: 1,
                }}
              >
                <div className="ds-calendar-day-event-time fw-bold mb-1" style={{ color }}>{ev.time}</div>
                <div className="ds-calendar-day-event-title fw-bold mb-1" style={{ color }}>{ev.title}</div>
                {ev.description && <div className="ds-calendar-day-event-description opacity-75" style={{ color }}>{ev.description}</div>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export const Calendar: React.FC<any> = ({
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

  React.useEffect(() => { if (viewValue) setActiveView(viewValue); }, [viewValue]);
  
  React.useEffect(() => { 
    const d = safeDate(currentDateValue); 
    if (d) setCurDate(d); 
  }, [currentDateValue]);

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
  const timeSlots    = React.useMemo(() => {
    const slots: string[] = [];
    for (let h = timeFrom; h < timeTo; h++) slots.push(`${String(h).padStart(2,'0')}:00`);
    return slots;
  }, [timeFrom, timeTo]);

  const dayTimeSlots = React.useMemo(() => {
    const slots: string[] = [];
    for (let h = timeFrom; h < timeTo; h++) {
      slots.push(`${String(h).padStart(2,'0')}:00`);
      slots.push(`${String(h).padStart(2,'0')}:30`);
    }
    return slots;
  }, [timeFrom, timeTo]);

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

  const onEventClick = React.useMemo(() => {
    if (!onEventClickProp || !onEventClickProp.name) return null;
    return (ev: any) => emitActionSpec(onEventClickProp, onAction, {
      ...(onEventClickProp.context || {}),
      event: ev, date: ev.date || '', time: ev.time || '', title: ev.title || '',
    });
  }, [onEventClickProp, onAction]);

  const customButtons = React.useMemo(() => {
    if (!Array.isArray(buttonsProp)) return [];
    return buttonsProp.map((btn: any) => ({
      label:   btn.label,
      variant: btn.variant || 'default',
      onCustomClick: (selContext: Record<string, any>) => {
        if (btn.action) emitActionSpec(btn.action, onAction, { ...(btn.action.context || {}), ...selContext });
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

  const onClear = () => {
    if (activeView === 'month') setSelDates([]);
    else if (activeView === 'week') setWeekSlots([]);
    else setDaySlots([]);
  };

  return (
    <div style={parseStyle(style)} className="ds-calendar calendar-container">
      <Pivot
        className="ds-tabs-nav ds-calendar-view-tabs"
        selectedKey={activeView}
        onLinkClick={(item) => {
          const key = item?.props.itemKey;
          if (key === 'month' || key === 'week' || key === 'day') switchView(key);
        }}
      >
        <PivotItem headerText="Month" itemKey="month" />
        <PivotItem headerText="Week" itemKey="week" />
        <PivotItem headerText="Day" itemKey="day" />
      </Pivot>

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
