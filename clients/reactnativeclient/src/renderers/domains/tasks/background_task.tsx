import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Icon } from '../../../components/a2ui/Icon';

const STATUS_ICON: Record<string, string> = {
  completed: 'ri-checkbox-circle-line',
  failed: 'ri-close-circle-line',
  interrupted: 'ri-close-circle-line',
  running: 'ri-loader-4-line',
  started: 'ri-time-line',
  waiting_confirmation: 'ri-question-line',
};

const STATUS_COLOR: Record<string, string> = {
  completed: '#3FB950',
  failed: '#FF7B72',
  interrupted: '#FF7B72',
  running: '#58A6FF',
  started: '#8B949E',
  waiting_confirmation: '#D29922',
};

export const BackgroundTask: React.FC<any> = ({ task_id, taskId, sendAction, backgroundTasks = {}, style }) => {
  const id = String(task_id || taskId || '').trim();
  const task = id ? backgroundTasks[id] : null;

  React.useEffect(() => {
    if (id && !task && typeof sendAction === 'function') {
      sendAction('background_task.get', { task_id: id });
    }
  }, [id, sendAction, task]);

  if (!id) return null;

  const status = String(task?.status || 'started');
  const label = String(task?.label || id);
  const progress = Math.max(0, Math.min(100, Math.round(Number(task?.progress || 0) * 100)));
  const isDone = ['completed', 'failed', 'interrupted'].includes(status);

  return (
    <View style={[styles.card, style]}>
      <View style={styles.row}>
        <Icon name={STATUS_ICON[status] || STATUS_ICON.started} size={18} color={STATUS_COLOR[status] || STATUS_COLOR.started} />
        <Text style={styles.label}>{label}</Text>
        <Text style={[styles.status, { color: STATUS_COLOR[status] || STATUS_COLOR.started }]}>{status}</Text>
      </View>
      {!isDone ? (
        <View style={styles.track}>
          <View style={[styles.fill, { width: `${progress}%` }]} />
        </View>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    padding: 10,
    marginVertical: 4,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  label: { flex: 1, color: '#E6EDF3', fontSize: 13, fontWeight: '600' },
  status: { fontSize: 11, fontWeight: '700' },
  track: { height: 5, borderRadius: 999, backgroundColor: '#30363D', overflow: 'hidden', marginTop: 8 },
  fill: { height: 5, borderRadius: 999, backgroundColor: '#58A6FF' },
});
