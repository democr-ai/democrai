import React from 'react';
import { Progress as UIProgress } from '@/components/ui/progress';
import { resolveIconClass } from '@/utils/icons';
import { useClientStateValue } from '@/state/clientState';
import { cn } from '@/lib/utils';
import {
  registerBackgroundTaskListener,
  unregisterBackgroundTaskListener,
} from '@/runtime/background_task_events';

const STATUS_ICONS: Record<string, string> = {
  started: 'ric.time-line',
  running: 'ric.loader-line',
  completed: 'ric.checkbox-circle-line',
  failed: 'ric.close-circle-line',
  interrupted: 'ric.close-circle-line',
  waiting_confirmation: 'ric.question-line',
};

const STATUS_COLORS: Record<string, string> = {
  completed: 'ui-tone-success',
  failed: 'ui-tone-danger',
  interrupted: 'ui-tone-danger',
  running: 'ui-tone-info',
  started: 'text-muted-foreground',
  waiting_confirmation: 'ui-tone-warning',
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
  const progress: number = Math.round((Number(task?.progress ?? 0)) * 100);
  const isDone = status === 'completed' || status === 'failed' || status === 'interrupted';

  const iconKey = STATUS_ICONS[status] ?? 'ric.time-line';
  const iconClass = resolveIconClass(iconKey);
  const colorClass = STATUS_COLORS[status] ?? 'text-muted-foreground';

  return (
    <div className="flex flex-col gap-2 rounded-md border bg-muted/30 px-3 py-2">
      <div className="flex items-center gap-2">
        <i className={cn(iconClass, colorClass, 'text-base', status === 'running' && 'animate-spin')} />
        <span className="text-sm font-medium">{label}</span>
      </div>
      {!isDone && (
        <UIProgress value={progress} className="h-1.5" />
      )}
    </div>
  );
};
