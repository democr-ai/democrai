import React from 'react';
import { Button, FormFeedback, FormGroup, Label } from 'design-react-kit';
import { parseStyle } from '@/utils/style';
import { getLiteral } from '@/renderers/shared';
import { AudioRecordingController, startBrowserAudioRecording } from '@/utils/audioRecording';
import { toLocalAttachmentValue } from '@/utils/uploads';
import { resolveMediaUrl } from '@/utils/media';

export const AudioRecorder: React.FC<any> = ({
  id,
  label,
  value = [],
  setInput,
  style,
  error,
  syncInitialInput = true,
  ingest = true,
}) => {
  const audioRecordingRef = React.useRef<AudioRecordingController | null>(null);
  const startedAtRef = React.useRef<number>(0);
  const [recording, setRecording] = React.useState(false);
  const [files, setFiles] = React.useState<any[]>(Array.isArray(value) ? value : []);
  const [recorderError, setRecorderError] = React.useState('');

  React.useEffect(() => {
    const nextFiles = Array.isArray(value) ? value : [];
    setFiles(nextFiles);
    if (syncInitialInput) setInput?.(id, nextFiles);
  }, [id, setInput, syncInitialInput, value]);

  React.useEffect(() => () => {
    audioRecordingRef.current?.cancel();
    files.forEach((file) => {
      const url = file?.preview_url || file?.url;
      if (typeof url === 'string' && url.startsWith('blob:')) URL.revokeObjectURL(url);
    });
  }, [files]);

  const commitFile = (file: File, durationSeconds: number) => {
    files.forEach((item) => {
      const url = item?.preview_url || item?.url;
      if (typeof url === 'string' && url.startsWith('blob:')) URL.revokeObjectURL(url);
    });
    const next = [{
      ...toLocalAttachmentValue(file),
      kind: 'audio',
      duration_seconds: durationSeconds,
      ingest: ingest !== false,
    }];
    setFiles(next);
    setInput?.(id, next);
  };

  const startRecording = async () => {
    setRecorderError('');
    try {
      audioRecordingRef.current = await startBrowserAudioRecording('recording');
    } catch (exc) {
      setRecorderError(exc instanceof Error ? exc.message : 'Unable to access the microphone');
      return;
    }
    startedAtRef.current = Date.now();
    setRecording(true);
  };

  const stopRecording = () => {
    const recordingController = audioRecordingRef.current;
    if (!recordingController) return;
    audioRecordingRef.current = null;
    recordingController
      .stop()
      .then((file) => {
        const durationSeconds = Math.max(0, Math.round((Date.now() - startedAtRef.current) / 10) / 100);
        commitFile(file, durationSeconds);
      })
      .catch((exc) => {
        setRecorderError(exc instanceof Error ? exc.message : 'Unable to record audio');
      })
      .finally(() => {
        setRecording(false);
      });
  };

  const removeRecording = () => {
    files.forEach((file) => {
      const url = file?.preview_url || file?.url;
      if (typeof url === 'string' && url.startsWith('blob:')) URL.revokeObjectURL(url);
    });
    setFiles([]);
    setInput?.(id, []);
  };

  const file = files[0];
  const rawSource = file?.preview_url || file?.url || file?.path;
  const source = typeof rawSource === 'string' ? resolveMediaUrl(rawSource) : rawSource;
  const labelText = getLiteral(label);
  const message = error || recorderError;

  return (
    <FormGroup className="a2ui-field a2ui-audio-recorder" style={parseStyle(style)}>
      {labelText && <Label for={id} className={message ? 'text-danger' : ''}>{labelText}</Label>}
      <div className="a2ui-audio-recorder-row">
        <Button
          type="button"
          color={recording ? 'danger' : 'primary'}
          onClick={recording ? stopRecording : startRecording}
          id={id}
          aria-label={recording ? 'Stop recording' : 'Start recording'}
          title={recording ? 'Stop recording' : 'Start recording'}
          className={`a2ui-button a2ui-audio-record-btn ${recording ? 'is-recording' : ''}`}
        >
          <i className={recording ? 'ri-stop-fill' : 'ri-mic-line'} aria-hidden="true" />
        </Button>
        <div className="a2ui-audio-recorder-body">
          <div className="a2ui-audio-recorder-status">
            {recording ? 'Recording...' : source ? 'Recording ready' : 'Ready to record'}
          </div>
          {file?.duration_seconds != null && <div className="text-muted xsmall">{file.duration_seconds}s</div>}
        </div>
        {source && (
          <div className="a2ui-audio-recorder-playback">
            <audio controls src={source} className="a2ui-audio-recorder-audio" />
            <Button
              type="button"
              size="sm"
              color="secondary"
              outline
              onClick={removeRecording}
              aria-label="Remove recording"
              title="Remove recording"
              className="a2ui-button a2ui-audio-remove-btn"
            >
              <i className="ri-close-line" aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>
      {message && <FormFeedback className="d-block mt-1">{message}</FormFeedback>}
    </FormGroup>
  );
};
