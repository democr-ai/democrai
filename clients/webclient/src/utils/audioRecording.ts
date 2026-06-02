export type AudioRecordingController = {
  stop: () => Promise<File>;
  cancel: () => void;
};

const MIME_CANDIDATES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
] as const;

function extensionForMime(mime: string): string {
  if (mime.includes('ogg')) return 'ogg';
  if (mime.includes('mp4')) return 'm4a';
  if (mime.includes('wav')) return 'wav';
  return 'webm';
}

function preferredMediaRecorderOptions(): MediaRecorderOptions | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  if (typeof MediaRecorder.isTypeSupported !== 'function') return undefined;
  const mimeType = MIME_CANDIDATES.find((candidate) => MediaRecorder.isTypeSupported(candidate));
  return mimeType ? { mimeType } : undefined;
}

function stopStream(stream: MediaStream): void {
  stream.getTracks().forEach((track) => track.stop());
}

function startMediaRecorder(stream: MediaStream, filenameBase: string): AudioRecordingController {
  const options = preferredMediaRecorderOptions();
  const recorder = options ? new MediaRecorder(stream, options) : new MediaRecorder(stream);
  const chunks: Blob[] = [];
  let settled = false;
  let resolveStop: ((file: File) => void) | null = null;
  let rejectStop: ((error: unknown) => void) | null = null;

  const stoppedPromise = new Promise<File>((resolve, reject) => {
    resolveStop = resolve;
    rejectStop = reject;
  });

  recorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  recorder.onerror = (event) => {
    if (settled) return;
    settled = true;
    stopStream(stream);
    rejectStop?.(event);
  };
  recorder.onstop = () => {
    if (settled) return;
    settled = true;
    const mime = recorder.mimeType || options?.mimeType || 'audio/webm';
    const blob = new Blob(chunks, { type: mime });
    stopStream(stream);
    resolveStop?.(new File([blob], `${filenameBase}.${extensionForMime(mime)}`, { type: mime }));
  };

  recorder.start();

  return {
    stop: () => {
      if (!settled && recorder.state !== 'inactive') recorder.stop();
      return stoppedPromise;
    },
    cancel: () => {
      if (!settled && recorder.state !== 'inactive') recorder.stop();
      stopStream(stream);
    },
  };
}

function encodeWav(samples: Float32Array[], sampleRate: number): Blob {
  const sampleCount = samples.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + sampleCount * 2);
  const view = new DataView(buffer);
  let offset = 0;

  const writeString = (value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset, value.charCodeAt(i));
      offset += 1;
    }
  };

  writeString('RIFF');
  view.setUint32(offset, 36 + sampleCount * 2, true);
  offset += 4;
  writeString('WAVE');
  writeString('fmt ');
  view.setUint32(offset, 16, true);
  offset += 4;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint32(offset, sampleRate, true);
  offset += 4;
  view.setUint32(offset, sampleRate * 2, true);
  offset += 4;
  view.setUint16(offset, 2, true);
  offset += 2;
  view.setUint16(offset, 16, true);
  offset += 2;
  writeString('data');
  view.setUint32(offset, sampleCount * 2, true);
  offset += 4;

  samples.forEach((chunk) => {
    for (let i = 0; i < chunk.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, chunk[i] || 0));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }
  });

  return new Blob([buffer], { type: 'audio/wav' });
}

function startWavRecorder(stream: MediaStream, filenameBase: string): AudioRecordingController {
  const AudioContextCtor = window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioContextCtor) {
    stopStream(stream);
    throw new Error('Audio recording is not supported by this browser');
  }

  const audioContext = new AudioContextCtor();
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const samples: Float32Array[] = [];
  let stopped = false;
  let stopPromise: Promise<File> | null = null;

  processor.onaudioprocess = (event) => {
    if (stopped) return;
    const input = event.inputBuffer.getChannelData(0);
    samples.push(new Float32Array(input));
  };

  source.connect(processor);
  processor.connect(audioContext.destination);

  const finish = async (): Promise<File> => {
    if (stopPromise) return stopPromise;
    stopPromise = (async () => {
      stopped = true;
      processor.disconnect();
      source.disconnect();
      stopStream(stream);
      await audioContext.close().catch(() => undefined);
      const blob = encodeWav(samples, audioContext.sampleRate);
      return new File([blob], `${filenameBase}.wav`, { type: 'audio/wav' });
    })();
    return stopPromise;
  };

  return {
    stop: finish,
    cancel: () => {
      void finish();
    },
  };
}

export async function startBrowserAudioRecording(filenameBase: string): Promise<AudioRecordingController> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('Audio recording is not supported by this browser');
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

  if (typeof MediaRecorder !== 'undefined') {
    try {
      return startMediaRecorder(stream, filenameBase);
    } catch {
      return startWavRecorder(stream, filenameBase);
    }
  }

  return startWavRecorder(stream, filenameBase);
}
