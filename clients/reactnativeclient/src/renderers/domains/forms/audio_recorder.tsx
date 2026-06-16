import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { emitActionSpec, getLiteral } from '../../shared';
import { Icon } from '../../../components/a2ui/Icon';

const fmtDuration = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};

export const AudioRecorder: React.FC<any> = ({
  id,
  label,
  value = [],
  action,
  onAction,
  setInput,
  style,
  error,
  multiple = true,
}) => {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder, 250);
  const [items, setItems] = React.useState<any[]>(Array.isArray(value) ? value : []);
  const [message, setMessage] = React.useState('');

  React.useEffect(() => {
    setItems(Array.isArray(value) ? value : []);
  }, [value]);

  const publish = (next: any[]) => {
    setItems(next);
    setInput?.(id, next);
    emitActionSpec(action, onAction, { [id]: next, value: next });
  };

  const start = async () => {
    setMessage('');
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setMessage('Microphone permission denied.');
      return;
    }
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record();
  };

  const stop = async () => {
    await recorder.stop();
    const uri = recorder.uri;
    if (!uri) return;
    const nextItem = {
      name: `recording-${Date.now()}.m4a`,
      uri,
      url: uri,
      type: 'audio/m4a',
      mimeType: 'audio/m4a',
      duration: recorderState.durationMillis,
    };
    publish(multiple ? [...items, nextItem] : [nextItem]);
  };

  const remove = (index: number) => {
    publish(items.filter((_item, itemIndex) => itemIndex !== index));
  };

  const shownError = getLiteral(error) || message;
  const isRecording = recorderState.isRecording;

  return (
    <View style={[styles.container, style]}>
      {getLiteral(label) ? <Text style={[styles.label, shownError && styles.labelError]}>{getLiteral(label)}</Text> : null}
      <View style={[styles.panel, shownError && styles.panelError]}>
        <TouchableOpacity
          style={[styles.recordButton, isRecording && styles.stopButton]}
          onPress={isRecording ? stop : start}
          activeOpacity={0.75}
        >
          <Icon name={isRecording ? 'ri-stop-fill' : 'ri-mic-line'} size={18} color="#FFFFFF" />
          <Text style={styles.recordText}>{isRecording ? `Stop ${fmtDuration(recorderState.durationMillis / 1000)}` : 'Record audio'}</Text>
        </TouchableOpacity>
        {items.map((item, index) => (
          <View key={`${id}_audio_${index}`} style={styles.item}>
            <Icon name="ri-file-music-line" size={18} color="#58A6FF" />
            <Text style={styles.itemText} numberOfLines={1}>{getLiteral(item?.name || `Recording ${index + 1}`)}</Text>
            <TouchableOpacity style={styles.removeButton} onPress={() => remove(index)} hitSlop={8}>
              <Icon name="ri-close-line" size={14} color="#FF7B72" />
            </TouchableOpacity>
          </View>
        ))}
        {!items.length && !isRecording ? <Text style={styles.empty}>No recordings</Text> : null}
      </View>
      {shownError ? <Text style={styles.errorText}>{shownError}</Text> : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { width: '100%', marginVertical: 6 },
  label: { fontSize: 13, fontWeight: '500', color: '#8B949E', marginBottom: 6 },
  labelError: { color: '#FF7B72' },
  panel: {
    borderWidth: 1,
    borderColor: '#30363D',
    borderRadius: 8,
    backgroundColor: '#161B22',
    padding: 10,
    gap: 8,
  },
  panelError: { borderColor: '#F85149', backgroundColor: '#2A1216' },
  recordButton: {
    minHeight: 38,
    borderRadius: 8,
    backgroundColor: '#1F6FEB',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  stopButton: { backgroundColor: '#DA3633' },
  recordText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },
  item: {
    minHeight: 36,
    borderRadius: 7,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#0D1117',
    paddingHorizontal: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  itemText: { flex: 1, color: '#C9D1D9', fontSize: 13 },
  removeButton: { width: 26, height: 26, alignItems: 'center', justifyContent: 'center' },
  empty: { color: '#6E7681', fontSize: 13 },
  errorText: { fontSize: 12, color: '#FF7B72', marginTop: 4 },
});
