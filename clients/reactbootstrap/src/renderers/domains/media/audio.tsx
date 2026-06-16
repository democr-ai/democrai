import React from 'react';
import { parseStyle } from '@/utils/style';
import { useResolvedMediaUrl } from '@/hooks/useResolvedMediaUrl';
import { getLiteral, toBoolean } from '@/renderers/shared';
import { Button } from 'design-react-kit';
import { useI18n } from '@/utils/i18n';

export const Audio: React.FC<any> = ({
  source,
  title,
  autoplay = false,
  muted = false,
  loop = false,
  controls = true,
  poster,
  width,
  height,
  style,
  stateModel,
  sendAction,
}) => {
  const messages = useI18n(stateModel);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = React.useState(false);
  const [currentTime, setCurrentTime] = React.useState(0);
  const [duration, setDuration] = React.useState(0);
  const [blocked, setBlocked] = React.useState(false);
  const [retryKey, setRetryKey] = React.useState(0);
  const resolvedSource = useResolvedMediaUrl(getLiteral(source));
  const resolvedPoster = useResolvedMediaUrl(getLiteral(poster));

  React.useEffect(() => {
    setBlocked(false);
  }, [resolvedSource]);
  const parsedWidth = Number(width);
  const safeWidth = Number.isFinite(parsedWidth) ? Math.max(parsedWidth, 320) : undefined;

  React.useEffect(() => {
    const node = audioRef.current;
    if (!node) return;
    node.muted = toBoolean(muted);
  }, [muted]);

  const togglePlayback = async () => {
    const node = audioRef.current;
    if (!node) return;
    if (node.paused) {
      await node.play();
      setPlaying(true);
      return;
    }
    node.pause();
    setPlaying(false);
  };

  const formatTime = (value: number) => {
    if (!Number.isFinite(value) || value <= 0) return '0:00';
    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  };

  const handleAudioError = () => {
    if (resolvedSource && resolvedSource.includes('/media/proxy')) {
      setBlocked(true);
      // Trigger notification refresh to update the badge immediately
      sendAction?.('get_notifications_count', {});
    }
  };

  const handleReload = () => {
    setBlocked(false);
    setRetryKey((k) => k + 1);
  };

  if (blocked) {
    return (
      <div style={{ ...parseStyle(style), width: safeWidth }}>
        <div className="d-flex align-items-center gap-4 rounded border bg-light p-4">
          <div className="d-flex h-16 w-16 align-items-center justify-content-center bg-white border rounded text-xl text-muted">♪</div>
          <div className="d-flex flex-column gap-2">
            <span className="small text-muted">{messages.blockedUrl}</span>
            <Button
              size="xs"
              outline
              color="primary"
              onClick={handleReload}
            >
              {messages.reload}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ ...parseStyle(style), width: safeWidth }} className="border rounded bg-white shadow-sm p-2">
      <audio
        key={`${resolvedSource}-${retryKey}`}
        ref={audioRef}
        src={resolvedSource}
        autoPlay={toBoolean(autoplay)}
        loop={toBoolean(loop)}
        muted={toBoolean(muted)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
        onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime || 0)}
        onError={handleAudioError}
      />

      <div className="d-flex gap-3 align-items-center">
        <div className="d-flex align-items-center justify-content-center overflow-hidden border rounded bg-light" style={{ width: '64px', height: '64px' }}>
          {resolvedPoster ? (
            <img src={resolvedPoster} alt={getLiteral(title || 'Audio artwork')} className="h-100 w-100 object-cover" />
          ) : (
            <span className="h3 text-muted m-0">♪</span>
          )}
        </div>

        <div className="flex-grow-1 min-vw-0">
          <div className="small fw-bold text-truncate">{getLiteral(title || 'Traccia audio')}</div>

          {toBoolean(controls) ? (
            <div className="mt-2 d-flex align-items-center gap-3">
              <Button size="xs" color="primary" className="rounded-circle p-2 d-flex align-items-center justify-content-center" style={{ width: '32px', height: '32px' }} onClick={() => { void togglePlayback(); }}>
                <i className={playing ? "ri-pause-fill" : "ri-play-fill"} />
              </Button>
              <div className="flex-grow-1 d-flex flex-column gap-1">
                <input
                  type="range"
                  className="form-range"
                  min={0}
                  max={duration || 0}
                  step="any"
                  value={currentTime}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    setCurrentTime(next);
                    if (audioRef.current) audioRef.current.currentTime = next;
                  }}
                />
                <div className="d-flex justify-content-between xsmall text-muted">
                  <span>{formatTime(currentTime)}</span>
                  <span>{formatTime(duration)}</span>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};
