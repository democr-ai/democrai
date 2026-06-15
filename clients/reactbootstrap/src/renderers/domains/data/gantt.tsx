import React from 'react';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { Card, CardBody, CardHeader, CardTitle } from 'design-react-kit';

type GanttRow = {
  id: string;
  label: string;
  start: Date;
  end: Date;
  status: string;
  statusLabel: string;
  progress: number;
  color: string;
  group: string;
  depth: number;
  parentId: string;
  hasChildren: boolean;
  expanded: boolean;
};

const STATUS_COLORS: Record<string, string> = {
  planned: 'var(--muted-foreground)',
  active: 'var(--primary)',
  running: 'var(--primary)',
  done: 'var(--ui-tone-success)',
  success: 'var(--ui-tone-success)',
  blocked: 'var(--ui-tone-warning)',
  warning: 'var(--ui-tone-warning)',
  risk: 'var(--ui-tone-danger)',
  error: 'var(--ui-tone-danger)',
};
const DAY_MS = 24 * 60 * 60 * 1000;

type ScaleSpec = {
  raw: string;
  unitMs: number;
  unitWidth: number;
  isDay: boolean;
};

type Tick = {
  key: string;
  label: string;
  left: number;
  width: number;
};

const parseScale = (raw: any): ScaleSpec => {
  const value = String(getLiteral(raw) || '1d').trim().toLowerCase();
  const aliases: Record<string, string> = {
    day: '1d',
    daily: '1d',
    hour: '1h',
    hourly: '1h',
    minute: '1m',
    minutely: '1m',
    second: '1s',
    secondly: '1s',
    millisecond: '1ms',
  };
  const token = aliases[value] || value || '1d';
  const match = token.match(/^(\d+)\s*(ms|s|m|h|d)$/);
  if (!match) return { raw: '1d', unitMs: DAY_MS, unitWidth: 28, isDay: true };
  const amount = Math.max(1, Number(match[1]) || 1);
  const unit = match[2];
  const multiplier = unit === 'ms' ? 1 : unit === 's' ? 1000 : unit === 'm' ? 60_000 : unit === 'h' ? 3_600_000 : DAY_MS;
  const unitMs = amount * multiplier;
  const unitWidth = unit === 'ms' ? 36 : unit === 's' ? 40 : unit === 'm' ? 48 : unit === 'h' ? 56 : 28;
  return { raw: `${amount}${unit}`, unitMs, unitWidth, isDay: unit === 'd' };
};

const toDate = (raw: any, scale: ScaleSpec): Date | null => {
  const value = String(raw || '').trim();
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  if (scale.isDay) date.setHours(0, 0, 0, 0);
  return date;
};

const unitsBetween = (a: Date, b: Date, scale: ScaleSpec) => Math.max(0, Math.floor((b.getTime() - a.getTime()) / scale.unitMs));
const addDays = (base: Date, days: number): Date => {
  const next = new Date(base.getTime() + (days * DAY_MS));
  next.setHours(0, 0, 0, 0);
  return next;
};

const clampProgress = (value: any): number => Math.max(0, Math.min(100, Number(value || 0)));

const parseDuration = (token: string): number | null => {
  const m = String(token || '').trim().toLowerCase().match(/^(\d+)\s*([dw])$/);
  if (!m) return null;
  const value = Number(m[1]);
  if (!Number.isFinite(value) || value <= 0) return null;
  return m[2] === 'w' ? value * 7 : value;
};

const parseMermaidItems = (mermaid: string): any[] => {
  const lines = String(mermaid || '').split('\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('%%'));
  if (!lines.length || lines[0].toLowerCase() !== 'gantt') return [];
  const byId = new Map<string, { start: Date; end: Date }>();
  const items: any[] = [];
  let section = '';
  let index = 0;
  for (const line of lines.slice(1)) {
    const low = line.toLowerCase();
    if (low.startsWith('title ') || low.startsWith('dateformat ') || low.startsWith('axisformat ') || low.startsWith('tickinterval ') || low.startsWith('excludes ')) continue;
    if (low.startsWith('section ')) { section = line.slice('section '.length).trim(); continue; }
    if (!line.includes(':')) continue;
    const [labelRaw, tailRaw] = line.split(':', 2);
    const label = labelRaw.trim();
    const tokens = tailRaw.split(',').map((token) => token.trim()).filter(Boolean);
    if (!label || !tokens.length) continue;
    let status = 'planned', taskId = '', start: Date | null = null, end: Date | null = null, durationDays: number | null = null, afterRef = '';
    for (const token of tokens) {
      const tokenLow = token.toLowerCase();
      const dateToken = toDate(token, parseScale('1d'));
      const durationToken = parseDuration(token);
      if (['done', 'active', 'crit', 'milestone'].includes(tokenLow)) {
        if (tokenLow === 'done') status = 'done';
        if (tokenLow === 'active') status = 'active';
        if (tokenLow === 'crit') status = 'risk';
        continue;
      }
      if (tokenLow.startsWith('after ')) { afterRef = token.slice(6).trim(); continue; }
      if (dateToken) { if (!start) start = dateToken; else end = dateToken; continue; }
      if (durationToken != null) { durationDays = durationToken; continue; }
      if (!taskId && /^[A-Za-z0-9_.-]+$/.test(token)) taskId = token;
    }
    if (!taskId) taskId = `task_${index + 1}`;
    if (!start && afterRef && byId.has(afterRef)) start = addDays(byId.get(afterRef)!.end, 1);
    if (!start) continue;
    if (!end && durationDays != null) end = addDays(start, Math.max(1, durationDays) - 1);
    if (!end) end = start;
    if (end.getTime() < start.getTime()) end = start;
    byId.set(taskId, { start, end });
    items.push({ id: taskId, label, group: section, start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10), status, progress: status === 'done' ? 100 : status === 'active' ? 55 : 0 });
    index += 1;
  }
  return items;
};

const parseRows = (rawItems: any[], scale: ScaleSpec, depth = 0, parentId = ''): GanttRow[] => {
  const rows: GanttRow[] = [];
  rawItems.forEach((raw: any, index: number) => {
    if (!raw || typeof raw !== 'object') return;
    const id = String(raw.id || `${parentId || 'task'}_${index + 1}`);
    const childrenRaw = Array.isArray(raw.subtasks) ? raw.subtasks : Array.isArray(raw.children) ? raw.children : [];
    const childRows = parseRows(childrenRaw, scale, depth + 1, id);
    const childStarts = childRows.map((row) => row.start.getTime());
    const childEnds = childRows.map((row) => row.end.getTime());
    let start = toDate(raw.start, scale), end = toDate(raw.end, scale);
    if (!start && childStarts.length > 0) start = new Date(Math.min(...childStarts));
    if (!end && childEnds.length > 0) end = new Date(Math.max(...childEnds));
    if (!start) return;
    if (!end || end.getTime() < start.getTime()) end = start;
    rows.push({ id, label: String(raw.label || raw.name || `Attività ${index + 1}`), start, end, status: String(raw.status || '').toLowerCase(), statusLabel: String(raw.status_label || raw.statusLabel || ''), progress: clampProgress(raw.progress), color: String(raw.color || ''), group: String(raw.group || ''), depth, parentId, hasChildren: childRows.length > 0, expanded: Boolean(raw.expanded) });
    rows.push(...childRows);
  });
  return rows;
};

const visibleRows = (rows: GanttRow[], expandedState: Record<string, boolean> = {}): GanttRow[] => {
  const byId = new Map(rows.map((row) => [row.id, row]));
  return rows.filter((row) => {
    let parent = row.parentId;
    while (parent) {
      const parentRow = byId.get(parent);
      const parentExpanded = expandedState[parent] ?? parentRow?.expanded ?? false;
      if (!parentRow || !parentExpanded) return false;
      parent = parentRow.parentId;
    }
    return true;
  });
};

const monthLabel = (date: Date): string =>
  new Intl.DateTimeFormat('it-IT', { month: 'short', year: 'numeric' }).format(date);

const shortDate = (date: Date): string =>
  new Intl.DateTimeFormat('it-IT', { month: 'short', day: '2-digit' }).format(date);

const shortInstant = (date: Date, scale: ScaleSpec): string => {
  if (scale.isDay) return shortDate(date);
  const options: Intl.DateTimeFormatOptions = scale.unitMs < 1000
    ? { hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 }
    : scale.unitMs < 60_000
      ? { hour: '2-digit', minute: '2-digit', second: '2-digit' }
      : scale.unitMs < DAY_MS
        ? { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }
        : { month: 'short', day: '2-digit' };
  return new Intl.DateTimeFormat('it-IT', options).format(date);
};

const tickLabel = (date: Date, scale: ScaleSpec): string => {
  if (scale.isDay) return shortDate(date);
  if (scale.unitMs < 1000) return date.toISOString().slice(17, 23);
  if (scale.unitMs < 60_000) return date.toLocaleTimeString('it-IT', { hour12: false, minute: '2-digit', second: '2-digit' });
  if (scale.unitMs < DAY_MS) return date.toLocaleTimeString('it-IT', { hour12: false, hour: '2-digit', minute: '2-digit' });
  return shortDate(date);
};

export const Gantt: React.FC<any> = ({ title, items = [], mermaid = '', start, end, scale = '1d', style, height = 420 }) => {
  const scaleSpec = React.useMemo(() => parseScale(scale), [scale]);
  const sourceItems = React.useMemo(() => {
    const inline = Array.isArray(items) ? items : [];
    if (inline.length > 0) return inline;
    return parseMermaidItems(getLiteral(mermaid));
  }, [items, mermaid]);

  const allRows = React.useMemo(() => parseRows(sourceItems, scaleSpec), [sourceItems, scaleSpec]);
  const [expandedRows, setExpandedRows] = React.useState<Record<string, boolean>>({});

  React.useEffect(() => {
    const next: Record<string, boolean> = {};
    allRows.forEach((row) => { if (row.hasChildren) next[row.id] = row.expanded; });
    setExpandedRows(next);
  }, [allRows]);

  const rows = React.useMemo(() => visibleRows(allRows, expandedRows), [allRows, expandedRows]);

  const range = React.useMemo(() => {
    const rowStarts = allRows.map((row) => row.start.getTime());
    const rowEnds = allRows.map((row) => row.end.getTime());
    const min = toDate(start, scaleSpec) || (rowStarts.length > 0 ? new Date(Math.min(...rowStarts)) : null);
    const max = toDate(end, scaleSpec) || (rowEnds.length > 0 ? new Date(Math.max(...rowEnds)) : null);
    if (!min || !max) return null;
    return { start: min, end: max.getTime() >= min.getTime() ? max : min };
  }, [allRows, start, end, scaleSpec]);

  const labelColWidth = 360, rowHeight = 52;
  const totalUnits = range ? Math.max(1, unitsBetween(range.start, range.end, scaleSpec) + 1) : 1;
  const timelineWidth = totalUnits * scaleSpec.unitWidth;

  const ticks = React.useMemo(() => {
    if (!range) return [] as Tick[];
    if (scaleSpec.isDay) {
      const out: Tick[] = [];
      let cursor = new Date(range.start.getFullYear(), range.start.getMonth(), 1);
      while (cursor.getTime() <= range.end.getTime()) {
        const mStart = cursor.getTime() < range.start.getTime() ? range.start : new Date(cursor);
        const mEnd = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0);
        const clampedEnd = mEnd.getTime() > range.end.getTime() ? range.end : mEnd;
        out.push({ key: `${cursor.getFullYear()}-${cursor.getMonth()}`, label: monthLabel(cursor), left: unitsBetween(range.start, mStart, scaleSpec) * scaleSpec.unitWidth, width: (unitsBetween(mStart, clampedEnd, scaleSpec) + 1) * scaleSpec.unitWidth });
        cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
      }
      return out;
    }
    const every = Math.max(1, Math.ceil(96 / scaleSpec.unitWidth), Math.ceil(totalUnits / 16));
    return Array.from({ length: totalUnits }, (_, index) => {
      const date = new Date(range.start.getTime() + index * scaleSpec.unitMs);
      return { key: `${scaleSpec.raw}-${index}`, label: index % every === 0 ? tickLabel(date, scaleSpec) : '', left: index * scaleSpec.unitWidth, width: index % every === 0 ? every * scaleSpec.unitWidth : scaleSpec.unitWidth };
    });
  }, [range, scaleSpec, totalUnits]);

  return (
    <Card style={parseStyle(style)} className="a2ui-gantt border overflow-hidden">
      {title && (
        <CardHeader className="a2ui-gantt-titlebar border-bottom">
          <CardTitle className="m-0 xsmall text-uppercase fw-bold">{getLiteral(title)}</CardTitle>
        </CardHeader>
      )}
      <CardBody className="p-0">
        {!range || rows.length === 0 ? (
          <div className="p-4 text-center text-muted small">Nessuna attività pianificata.</div>
        ) : (
          <div className="a2ui-gantt-scroll overflow-auto" style={{ maxHeight: Math.max(260, Number(height) || 420) }}>
            <div style={{ minWidth: labelColWidth + timelineWidth }}>
              <div className="a2ui-gantt-head sticky-top z-index-10 d-flex font-monospace xsmall fw-bold">
                <div className="a2ui-gantt-head-label flex-shrink-0 text-uppercase" style={{ width: labelColWidth }}>Activities</div>
                <div className="a2ui-gantt-head-timeline position-relative" style={{ width: timelineWidth, height: '40px' }}>
                  {ticks.map(tick => (
                    <div key={tick.key} className="a2ui-gantt-tick position-absolute text-uppercase" style={{ left: tick.left, width: tick.width }}>{tick.label}</div>
                  ))}
                </div>
              </div>

              {rows.map(row => {
                const color = row.color || STATUS_COLORS[row.status] || STATUS_COLORS.planned;
                const isExpanded = expandedRows[row.id] ?? row.expanded;
                const barLeft = unitsBetween(range.start, row.start, scaleSpec) * scaleSpec.unitWidth;
                const barWidth = Math.min(
                  Math.max(scaleSpec.unitWidth, (unitsBetween(row.start, row.end, scaleSpec) + 1) * scaleSpec.unitWidth),
                  Math.max(scaleSpec.unitWidth, timelineWidth - barLeft),
                );
                const barText = barWidth >= 64 ? row.statusLabel || row.status.toUpperCase() || row.label : '';
                const statusText = row.statusLabel || row.status || 'planned';
                return (
                  <div key={row.id} className="a2ui-gantt-row d-flex" style={{ minHeight: rowHeight }}>
                    <div className="a2ui-gantt-label flex-shrink-0 d-flex flex-column justify-content-center overflow-hidden" style={{ width: labelColWidth }}>
                      <div className="d-flex align-items-center gap-2 overflow-hidden text-nowrap" style={{ paddingLeft: row.depth * 16 }}>
                        {row.hasChildren && (
                          <button type="button" className="a2ui-gantt-expand" onClick={() => setExpandedRows(p => ({ ...p, [row.id]: !isExpanded }))} aria-label={isExpanded ? 'Collapse row' : 'Expand row'}>
                            <i className={isExpanded ? "ri-arrow-down-s-fill" : "ri-arrow-right-s-fill"} />
                          </button>
                        )}
                        <span className="a2ui-gantt-row-title text-truncate small fw-bold">{row.label}</span>
                        <span className="a2ui-gantt-status ms-auto" style={{ borderColor: color, color }}>{statusText}</span>
                      </div>
                      <div className="a2ui-gantt-row-meta xsmall mt-1 text-truncate" style={{ paddingLeft: row.depth * 16 + (row.hasChildren ? 26 : 0), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {row.group ? `${row.group} · ` : ''}{shortInstant(row.start, scaleSpec)} - {shortInstant(row.end, scaleSpec)} · {row.progress}%
                      </div>
                    </div>
                    <div className="a2ui-gantt-timeline position-relative flex-grow-1" style={{ width: timelineWidth, '--gantt-unit': `${scaleSpec.unitWidth}px` } as React.CSSProperties}>
                      <div className="a2ui-gantt-bar position-absolute top-50 translate-middle-y overflow-hidden" style={{ left: barLeft, width: barWidth, borderColor: color }}>
                        <div className="a2ui-gantt-progress h-100 transition-all" style={{ width: `${row.progress}%`, backgroundColor: color }} />
                        {barText && <span className="a2ui-gantt-bar-text position-absolute top-0 bottom-0 start-0 d-flex align-items-center px-2 fw-bold">{barText}</span>}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
};
