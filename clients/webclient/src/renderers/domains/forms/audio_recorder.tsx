import React from 'react';
import { Mic, Square, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
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
      setRecorderError(exc instanceof Error ? exc.message : 'Unable to access microphone');
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
  const message = error || recorderError;

  return (
    <div className="grid gap-2" style={parseStyle(style)}>
      {getLiteral(label) ? <Label className={cn(message && 'text-destructive')}>{getLiteral(label)}</Label> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant={recording ? 'destructive' : 'default'} size="sm" onClick={recording ? stopRecording : startRecording}>
          {recording ? <Square className="mr-2 h-4 w-4" /> : <Mic className="mr-2 h-4 w-4" />}
          {recording ? 'Stop' : 'Record'}
        </Button>
        {source ? (
          <>
            <audio controls src={source} />
            <Button type="button" variant="outline" size="sm" onClick={removeRecording}>
              <X className="mr-2 h-4 w-4" />
              Remove
            </Button>
          </>
        ) : null}
      </div>
      {file?.duration_seconds != null ? <p className="text-xs text-muted-foreground">{file.duration_seconds}s</p> : null}
      {message ? <p className="text-sm text-destructive">{message}</p> : null}
    </div>
  );
};
