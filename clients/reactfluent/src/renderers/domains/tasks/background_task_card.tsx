import React from 'react';
import { useClientStateValue } from '@/state/clientState';
import { cn } from '@/lib/utils';
import {
  registerBackgroundTaskListener,
  unregisterBackgroundTaskListener,
} from '@/runtime/background_task_events';

const STATUS_ICONS: Record<string, string> = {
  started: 'ri-time-line',
  running: 'ri-loader-line',
  completed: 'ri-checkbox-circle-line',
  failed: 'ri-close-circle-line',
  interrupted: 'ri-close-circle-line',
  waiting_confirmation: 'ri-question-line',
};

const STATUS_COLORS: Record<string, string> = {
  completed: 'is-completed',
  failed: 'is-failed',
  interrupted: 'is-failed',
  running: 'is-running',
  started: 'is-started',
  waiting_confirmation: 'is-waiting',
};

const normalizeProgress = (raw: unknown): number => {
  const parsed = Number(raw ?? 0);
  if (!Number.isFinite(parsed)) return 0;
  const pct = parsed <= 1 ? parsed * 100 : parsed;
  return Math.max(0, Math.min(100, Math.round(pct)));
};

export const BackgroundTaskCard: React.FC<{
  task_id: string;
  sendAction: (name: string, ctx: any) => void;
  onAction?: (name: string, ctx: any) => void;
  on_finish?: any;
  on_started?: any;
  on_progress?: any;
  on_completed?: any;
  on_error?: any;
  on_confirmation?: any;
  on_update?: any;
  on_event_notification?: any;
}> = ({
  task_id,
  sendAction,
  onAction,
  on_finish,
  on_started,
  on_progress,
  on_completed,
  on_error,
  on_confirmation,
  on_update,
  on_event_notification,
}) => {
  const task = useClientStateValue(`background_tasks/${task_id}`, 'global');
  const listenerId = React.useId();

  React.useEffect(() => {
    if (!task_id) return;
    if (!task) {
      sendAction('background_task.get', { task_id });
    }
  }, [task_id, task, sendAction]);

  React.useEffect(() => {
    if (!task_id || !onAction) return;
    registerBackgroundTaskListener(listenerId, {
      taskId: task_id,
      actions: {
        on_finish,
        on_started,
        on_progress,
        on_completed,
        on_error,
        on_confirmation,
        on_update,
        on_event_notification,
      },
      onAction,
    });
    return () => unregisterBackgroundTaskListener(listenerId);
  }, [
    listenerId,
    onAction,
    on_completed,
    on_confirmation,
    on_error,
    on_event_notification,
    on_finish,
    on_progress,
    on_started,
    on_update,
    task_id,
  ]);

  if (!task_id) return null;

  const status: string = task?.status ?? 'started';
  const label: string = task?.label ?? task_id;
  const progress: number = normalizeProgress(task?.progress ?? task?.progress_percent ?? task?.percentage);
  const isDone = status === 'completed' || status === 'failed' || status === 'interrupted';
  const showProgress = task ? true : !isDone;

  const iconClass = STATUS_ICONS[status] ?? 'ri-time-line';
  const colorClass = STATUS_COLORS[status] ?? 'text-muted';

  return (
    <div className="a2ui-background-task-card">
      <div className="a2ui-background-task-header">
        <span className={cn('a2ui-background-task-icon', colorClass, (status === 'running' || status === 'started') && 'is-spinning')} aria-hidden="true">
          <i className={iconClass} />
        </span>
        <span className="a2ui-background-task-label">{label}</span>
        <span className={cn('a2ui-background-task-status', colorClass)}>{status.replace(/_/g, ' ')}</span>
      </div>
      {showProgress && (
        <div className="a2ui-background-task-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
          <div
            className={cn('a2ui-background-task-progress-bar', (status === 'running' || status === 'started') && 'is-animated')}
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
      {showProgress && <div className="a2ui-background-task-percent">{progress}%</div>}
    </div>
  );
};
