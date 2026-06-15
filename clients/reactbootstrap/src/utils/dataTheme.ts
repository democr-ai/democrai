const cssVar = (name: string): string => `var(${name})`;

export const DATA_THEME = {
  status: {
    planned: cssVar('--data-status-planned'),
    active: cssVar('--data-status-active'),
    blocked: cssVar('--data-status-blocked'),
    done: cssVar('--data-status-done'),
    risk: cssVar('--data-status-risk'),
  },
  surface: {
    base: cssVar('--data-surface-base'),
    panel: cssVar('--data-surface-panel'),
    border: cssVar('--data-surface-border'),
  },
  text: {
    primary: cssVar('--data-text-primary'),
    muted: cssVar('--data-text-muted'),
    subtle: cssVar('--data-text-subtle'),
    soft: cssVar('--data-text-soft'),
  },
} as const;

export const WORKFLOW_THEME = {
  nodeFill: cssVar('--workflow-node-fill'),
  nodeStroke: cssVar('--workflow-node-stroke'),
  nodeText: cssVar('--workflow-node-text'),
  dragStroke: DATA_THEME.status.active,
  nodeShadow: cssVar('--workflow-node-shadow'),
  nodeShadowSelected: cssVar('--workflow-node-shadow-selected'),
  handleBorder: cssVar('--workflow-handle-border'),
  handleIn: cssVar('--workflow-handle-in'),
  handleOut: cssVar('--workflow-handle-out'),
} as const;

export const DIAGRAM_THEME = {
  nodeFill: cssVar('--diagram-node-fill'),
  nodeStroke: cssVar('--diagram-node-stroke'),
  nodeText: cssVar('--diagram-node-text'),
} as const;

export const CALENDAR_THEME = {
  bg: cssVar('--calendar-bg'),
  border: cssVar('--calendar-border'),
  selectedBg: cssVar('--calendar-selected-bg'),
  selectedBorder: cssVar('--calendar-selected-border'),
  slotSelected: cssVar('--calendar-slot-selected'),
  actionbarBg: cssVar('--calendar-actionbar-bg'),
  actionbarBorder: cssVar('--calendar-actionbar-border'),
  textTitle: cssVar('--calendar-text-title'),
  textNav: cssVar('--calendar-text-nav'),
  textSub: cssVar('--calendar-text-sub'),
  textHeader: cssVar('--calendar-text-header'),
  eventFallback: DATA_THEME.status.planned,
} as const;

export function dataStatusColor(status: string, fallback = DIAGRAM_THEME.nodeStroke): string {
  const key = String(status || '').trim().toLowerCase();
  if (key === 'running') return DATA_THEME.status.active;
  if (key === 'success' || key === 'done') return DATA_THEME.status.done;
  if (key === 'warning' || key === 'blocked') return DATA_THEME.status.blocked;
  if (key === 'error' || key === 'risk') return DATA_THEME.status.risk;
  if (key === 'planned' || key === 'queued' || key === 'active') {
    return (DATA_THEME.status as Record<string, string>)[key] || DATA_THEME.status.planned;
  }
  return fallback;
}
